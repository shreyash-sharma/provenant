"""ccusage adapter.

Reads local coding-agent usage through ccusage JSON reports and normalizes the
result into a Provenant-owned shape. ccusage is optional: this module never
imports it as a Python dependency.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


class CcusageError(RuntimeError):
    """Raised when ccusage cannot be executed or returns invalid output."""


@dataclass
class UsageRow:
    report_type: str
    date: str | None = None
    project: str | None = None
    agent: str | None = None
    model: str | None = None
    session_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    total_tokens: int = 0
    total_cost: float | None = None
    first_activity: str | None = None
    last_activity: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageSnapshot:
    source: str
    since: str | None
    until: str | None
    reports: list[str]
    totals: dict[str, Any]
    rows: list[UsageRow]
    raw: dict[str, Any]


def ccusage_available() -> dict[str, Any]:
    """Return availability details without running ccusage."""
    ccusage = shutil.which("ccusage")
    npx = shutil.which("npx")
    return {
        "available": bool(ccusage),
        "ccusage_path": ccusage,
        "npx_path": npx,
    }


def collect_ccusage(
    *,
    since: str | None = None,
    until: str | None = None,
    include_sessions: bool = True,
    include_blocks: bool = False,
    use_npx: bool = False,
    offline: bool = True,
    timeout_seconds: int = 90,
) -> UsageSnapshot:
    """Collect and normalize ccusage reports."""
    runner = _resolve_runner(use_npx=use_npx)
    raw: dict[str, Any] = {}
    rows: list[UsageRow] = []
    reports: list[str] = []

    daily = _run_ccusage(
        runner,
        ["daily", "--by-agent"],
        since=since,
        until=until,
        offline=offline,
        timeout_seconds=timeout_seconds,
    )
    raw["daily"] = daily
    reports.append("daily")
    rows.extend(_normalize_daily(daily))

    if include_sessions:
        sessions = _run_ccusage(
            runner,
            ["session"],
            since=since,
            until=until,
            offline=offline,
            timeout_seconds=timeout_seconds,
        )
        raw["session"] = sessions
        reports.append("session")
        rows.extend(_normalize_sessions(sessions))

    if include_blocks:
        blocks = _run_ccusage(
            runner,
            ["blocks"],
            since=since,
            until=until,
            offline=offline,
            timeout_seconds=timeout_seconds,
        )
        raw["blocks"] = blocks
        reports.append("blocks")
        rows.extend(_normalize_blocks(blocks))

    totals = _sum_rows(rows)
    return UsageSnapshot(
        source="ccusage",
        since=since,
        until=until,
        reports=reports,
        totals=totals,
        rows=rows,
        raw=raw,
    )


def _resolve_runner(*, use_npx: bool) -> list[str]:
    if not use_npx:
        exe = shutil.which("ccusage")
        if not exe:
            raise CcusageError("ccusage is not installed. Install it or rerun with --use-npx.")
        return [exe]

    npx = shutil.which("npx")
    if not npx:
        raise CcusageError("npx is not installed, and ccusage was not requested directly.")
    return [npx, "-y", "ccusage@latest"]


def _run_ccusage(
    runner: list[str],
    args: list[str],
    *,
    since: str | None,
    until: str | None,
    offline: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    cmd = [*runner, *args, "--json"]
    if offline:
        cmd.append("--offline")
    if since:
        cmd.extend(["--since", since])
    if until:
        cmd.extend(["--until", until])

    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise CcusageError(f"ccusage executable not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CcusageError(f"ccusage timed out after {timeout_seconds}s") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise CcusageError(detail or f"ccusage exited with code {proc.returncode}")

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise CcusageError("ccusage returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise CcusageError("ccusage JSON root was not an object")
    return parsed


def _normalize_daily(data: dict[str, Any]) -> list[UsageRow]:
    rows: list[UsageRow] = []
    projects = data.get("projects")
    if isinstance(projects, dict):
        for project, entries in projects.items():
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        rows.extend(_row_with_breakdowns("daily", entry, project=str(project)))
        return rows

    entries = data.get("daily") or data.get("data") or []
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                rows.extend(_row_with_breakdowns("daily", entry))
    return rows


def _normalize_sessions(data: dict[str, Any]) -> list[UsageRow]:
    rows: list[UsageRow] = []
    entries = data.get("sessions") or data.get("data") or []
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                rows.extend(_row_with_breakdowns("session", entry))
    return rows


def _normalize_blocks(data: dict[str, Any]) -> list[UsageRow]:
    rows: list[UsageRow] = []
    entries = data.get("blocks") or data.get("data") or []
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                rows.append(_base_row("block", entry))
    return rows


def _row_with_breakdowns(report_type: str, entry: dict[str, Any], project: str | None = None) -> list[UsageRow]:
    rows = [_base_row(report_type, entry, project=project)]

    agents = entry.get("agents")
    if isinstance(agents, list):
        for agent in agents:
            if isinstance(agent, dict):
                rows.append(_base_row("agent", agent, project=project, agent=_str_or_none(agent.get("agent") or agent.get("name"))))

    breakdowns = entry.get("modelBreakdowns") or entry.get("breakdown")
    if isinstance(breakdowns, list):
        for item in breakdowns:
            if isinstance(item, dict):
                rows.append(
                    _base_row(
                        "model",
                        item,
                        project=project,
                        agent=_str_or_none(entry.get("agent")),
                        model=_str_or_none(item.get("model") or item.get("modelName") or item.get("name")),
                    )
                )
    elif isinstance(breakdowns, dict):
        for model, item in breakdowns.items():
            if isinstance(item, dict):
                rows.append(_base_row("model", item, project=project, model=str(model)))
    return rows


def _base_row(
    report_type: str,
    entry: dict[str, Any],
    *,
    project: str | None = None,
    agent: str | None = None,
    model: str | None = None,
) -> UsageRow:
    return UsageRow(
        report_type=report_type,
        date=_str_or_none(
            entry.get("date")
            or entry.get("month")
            or entry.get("period")
            or entry.get("blockStart")
            or entry.get("startTime")
        ),
        project=project or _str_or_none(entry.get("project") or entry.get("instance")),
        agent=agent or _str_or_none(entry.get("agent") or entry.get("source")),
        model=model or _first_model(entry),
        session_id=_str_or_none(entry.get("sessionId") or entry.get("session") or entry.get("period")),
        input_tokens=_int(_field(entry, "inputTokens", "input_tokens")),
        output_tokens=_int(_field(entry, "outputTokens", "output_tokens")),
        cache_creation_tokens=_int(_field(entry, "cacheCreationTokens", "cache_creation_tokens", "cacheCreationInputTokens")),
        cache_read_tokens=_int(_field(entry, "cacheReadTokens", "cache_read_tokens", "cacheReadInputTokens")),
        total_tokens=_total_tokens(entry),
        total_cost=_float(entry.get("totalCost") or entry.get("costUSD") or entry.get("cost_usd") or entry.get("cost")),
        first_activity=_str_or_none(entry.get("firstActivity") or entry.get("blockStart") or entry.get("startTime")),
        last_activity=_str_or_none(
            entry.get("lastActivity")
            or entry.get("blockEnd")
            or entry.get("endTime")
            or _metadata_value(entry, "lastActivity")
        ),
        raw=entry,
    )


def _sum_rows(rows: list[UsageRow]) -> dict[str, Any]:
    primary = [r for r in rows if r.report_type == "daily"]
    if not primary:
        primary = [r for r in rows if r.report_type == "session"]
    if not primary:
        primary = [r for r in rows if r.report_type == "block"]
    return {
        "input_tokens": sum(r.input_tokens for r in primary),
        "output_tokens": sum(r.output_tokens for r in primary),
        "cache_creation_tokens": sum(r.cache_creation_tokens for r in primary),
        "cache_read_tokens": sum(r.cache_read_tokens for r in primary),
        "total_tokens": sum(r.total_tokens for r in primary),
        "total_cost": round(sum(r.total_cost or 0.0 for r in primary), 6),
    }


def _first_model(entry: dict[str, Any]) -> str | None:
    models = entry.get("modelsUsed") or entry.get("models")
    if isinstance(models, list) and models:
        return str(models[0])
    value = entry.get("model") or entry.get("modelName")
    return str(value) if value is not None else None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _total_tokens(entry: dict[str, Any]) -> int:
    explicit = _int(entry.get("totalTokens") or entry.get("total_tokens"))
    if explicit:
        return explicit
    return (
        _int(_field(entry, "inputTokens", "input_tokens"))
        + _int(_field(entry, "outputTokens", "output_tokens"))
        + _int(_field(entry, "cacheCreationTokens", "cache_creation_tokens", "cacheCreationInputTokens"))
        + _int(_field(entry, "cacheReadTokens", "cache_read_tokens", "cacheReadInputTokens"))
    )


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _field(entry: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in entry:
            return entry.get(name)
    token_counts = entry.get("tokenCounts")
    if isinstance(token_counts, dict):
        for name in names:
            if name in token_counts:
                return token_counts.get(name)
    return None


def _metadata_value(entry: dict[str, Any], name: str) -> Any:
    metadata = entry.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(name)
    return None
