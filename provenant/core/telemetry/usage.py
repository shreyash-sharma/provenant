"""Persistence helpers for external agent-usage telemetry."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from provenant.core.persistence.database import get_session
from provenant.core.persistence.models import AgentUsageRow, AgentUsageSnapshot, ProvenantUsageEvent
from provenant.core.telemetry.adapters.ccusage import UsageSnapshot

_CORRELATION_TOLERANCE = timedelta(minutes=5)


async def save_usage_snapshot(
    session_factory: async_sessionmaker,
    snapshot: UsageSnapshot,
    *,
    repository_id: str | None,
) -> dict[str, Any]:
    """Persist a normalized usage snapshot and return a summary."""
    async with get_session(session_factory) as session:
        db_snapshot = AgentUsageSnapshot(
            repository_id=repository_id,
            source=snapshot.source,
            reports_json=json.dumps(snapshot.reports),
            since=snapshot.since,
            until=snapshot.until,
            totals_json=json.dumps(snapshot.totals),
            raw_json=json.dumps(snapshot.raw),
        )
        session.add(db_snapshot)
        await session.flush()

        for row in snapshot.rows:
            session.add(
                AgentUsageRow(
                    snapshot_id=db_snapshot.id,
                    repository_id=repository_id,
                    report_type=row.report_type,
                    date=row.date,
                    project=row.project,
                    agent=row.agent,
                    model=row.model,
                    session_id=row.session_id,
                    input_tokens=row.input_tokens,
                    output_tokens=row.output_tokens,
                    cache_creation_tokens=row.cache_creation_tokens,
                    cache_read_tokens=row.cache_read_tokens,
                    total_tokens=row.total_tokens,
                    total_cost=row.total_cost,
                    first_activity=row.first_activity,
                    last_activity=row.last_activity,
                    raw_json=json.dumps(row.raw),
                )
            )

        return {
            "id": db_snapshot.id,
            "source": db_snapshot.source,
            "reports": snapshot.reports,
            "row_count": len(snapshot.rows),
            "totals": snapshot.totals,
            "created_at": db_snapshot.created_at.isoformat() if db_snapshot.created_at else None,
        }


async def latest_usage_snapshot(
    session_factory: async_sessionmaker,
    *,
    repository_id: str | None,
) -> dict[str, Any] | None:
    """Return the latest persisted usage snapshot with rows and group totals."""
    async with get_session(session_factory) as session:
        query = select(AgentUsageSnapshot)
        if repository_id is not None:
            query = query.where(AgentUsageSnapshot.repository_id == repository_id)
        query = query.order_by(desc(AgentUsageSnapshot.created_at)).limit(1)
        snap = (await session.execute(query)).scalar_one_or_none()
        if snap is None:
            return None

        row_query = select(AgentUsageRow).where(AgentUsageRow.snapshot_id == snap.id)
        row_query = row_query.order_by(AgentUsageRow.report_type, AgentUsageRow.date)
        rows = list((await session.execute(row_query)).scalars().all())

        event_query = select(ProvenantUsageEvent)
        if repository_id is not None:
            event_query = event_query.where(ProvenantUsageEvent.repository_id == repository_id)
        event_query = event_query.order_by(ProvenantUsageEvent.started_at.desc()).limit(1000)
        events = list((await session.execute(event_query)).scalars().all())

    serialized_rows = [_serialize_row(r) for r in rows]
    serialized_events = [_serialize_event(e) for e in events]
    return {
        "snapshot": {
            "id": snap.id,
            "source": snap.source,
            "reports": _loads(snap.reports_json, []),
            "since": snap.since,
            "until": snap.until,
            "totals": _loads(snap.totals_json, {}),
            "created_at": snap.created_at.isoformat() if snap.created_at else None,
        },
        "rows": serialized_rows,
        "provenant_events": serialized_events,
        "savings": _correlate_savings(serialized_rows, serialized_events),
        "groups": {
            "daily": _group(serialized_rows, "date", include=("daily",)),
            "project": _group(serialized_rows, "project", include=("daily",)),
            "agent": _group(serialized_rows, "agent", include=("agent",)),
            "model": _group(serialized_rows, "model", include=("model",)),
            "session": _group(serialized_rows, "session_id", include=("session",)),
        },
    }


async def usage_status(
    session_factory: async_sessionmaker,
    *,
    repository_id: str | None,
) -> dict[str, Any]:
    """Return whether persisted usage exists and when it was last synced."""
    from provenant.core.telemetry.adapters.ccusage import ccusage_available

    async with get_session(session_factory) as session:
        query = select(AgentUsageSnapshot)
        if repository_id is not None:
            query = query.where(AgentUsageSnapshot.repository_id == repository_id)
        query = query.order_by(desc(AgentUsageSnapshot.created_at)).limit(1)
        snap = (await session.execute(query)).scalar_one_or_none()

    availability = ccusage_available()
    return {
        **availability,
        "has_data": snap is not None,
        "last_sync_at": snap.created_at.isoformat() if snap and snap.created_at else None,
        "last_snapshot_id": snap.id if snap else None,
    }


def _serialize_row(row: AgentUsageRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "report_type": row.report_type,
        "date": row.date,
        "project": row.project,
        "agent": row.agent,
        "model": row.model,
        "session_id": row.session_id,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "cache_creation_tokens": row.cache_creation_tokens,
        "cache_read_tokens": row.cache_read_tokens,
        "total_tokens": row.total_tokens,
        "total_cost": row.total_cost,
        "first_activity": row.first_activity,
        "last_activity": row.last_activity,
    }


def _serialize_event(event: ProvenantUsageEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "repository_id": event.repository_id,
        "tool_name": event.tool_name,
        "started_at": event.started_at.isoformat() if event.started_at else None,
        "finished_at": event.finished_at.isoformat() if event.finished_at else None,
        "duration_ms": event.duration_ms,
        "query_text": event.query_text,
        "target_count": event.target_count,
        "returned_target_count": event.returned_target_count,
        "estimated_context_tokens": event.estimated_context_tokens,
        "success": event.success,
        "error_type": event.error_type,
        "client_name": event.client_name,
    }


def _correlate_savings(
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    session_rows = [row for row in rows if row.get("report_type") == "session"]
    parsed_events = [
        (event, _parse_dt(event.get("started_at")))
        for event in events
        if _parse_dt(event.get("started_at")) is not None
    ]

    assisted: list[dict[str, Any]] = []
    unassisted: list[dict[str, Any]] = []
    uncorrelated = 0

    for row in session_rows:
        first = _parse_dt(row.get("first_activity"))
        last = _parse_dt(row.get("last_activity"))
        if first is None or last is None:
            uncorrelated += 1
            continue
        window_start = first - _CORRELATION_TOLERANCE
        window_end = last + _CORRELATION_TOLERANCE
        has_event = any(
            event_at is not None and window_start <= event_at <= window_end
            for _, event_at in parsed_events
        )
        if has_event:
            assisted.append(row)
        else:
            unassisted.append(row)

    assisted_totals = _totals_for(assisted)
    unassisted_totals = _totals_for(unassisted)
    return {
        "mode": "automatic_correlation",
        "label": "Observed Provenant-assisted usage",
        "tolerance_minutes": int(_CORRELATION_TOLERANCE.total_seconds() // 60),
        "assisted": assisted_totals,
        "unassisted": unassisted_totals,
        "observed_delta": _observed_delta(assisted_totals, unassisted_totals),
        "event_count": len(events),
        "successful_event_count": sum(1 for e in events if e.get("success")),
        "estimated_context_tokens": sum(int(e.get("estimated_context_tokens") or 0) for e in events),
        "top_tools": _top_tools(events),
        "uncorrelated_sessions": uncorrelated,
    }


def _totals_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "sessions": len(rows),
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
    }
    for row in rows:
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_tokens",
            "cache_read_tokens",
            "total_tokens",
        ):
            totals[key] += int(row.get(key) or 0)
        totals["total_cost"] += float(row.get("total_cost") or 0.0)
    sessions = max(totals["sessions"], 1)
    totals["avg_tokens_per_session"] = totals["total_tokens"] / sessions
    totals["avg_cost_per_session"] = totals["total_cost"] / sessions
    return totals


def _observed_delta(assisted: dict[str, Any], unassisted: dict[str, Any]) -> dict[str, Any]:
    return {
        "avg_token_reduction_pct": _pct_drop(
            unassisted.get("avg_tokens_per_session"),
            assisted.get("avg_tokens_per_session"),
        ),
        "avg_cost_reduction_pct": _pct_drop(
            unassisted.get("avg_cost_per_session"),
            assisted.get("avg_cost_per_session"),
        ),
    }


def _pct_drop(baseline: Any, treatment: Any) -> float | None:
    try:
        baseline_f = float(baseline or 0)
        treatment_f = float(treatment or 0)
    except Exception:
        return None
    if baseline_f <= 0:
        return None
    return round((baseline_f - treatment_f) / baseline_f * 100.0, 1)


def _top_tools(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"tool_name": "", "calls": 0, "estimated_context_tokens": 0})
    for event in events:
        name = str(event.get("tool_name") or "unknown")
        bucket = counts[name]
        bucket["tool_name"] = name
        bucket["calls"] += 1
        bucket["estimated_context_tokens"] += int(event.get("estimated_context_tokens") or 0)
    return sorted(counts.values(), key=lambda item: item["calls"], reverse=True)[:5]


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _group(rows: list[dict[str, Any]], key: str, *, include: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "key": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "rows": 0,
    })
    for row in rows:
        if row["report_type"] not in include:
            continue
        raw_key = row.get(key) or "unknown"
        bucket = grouped[str(raw_key)]
        bucket["key"] = str(raw_key)
        bucket["rows"] += 1
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_creation_tokens",
            "cache_read_tokens",
            "total_tokens",
        ):
            bucket[field] += int(row.get(field) or 0)
        bucket["total_cost"] += float(row.get("total_cost") or 0.0)
    return sorted(grouped.values(), key=lambda item: item["total_tokens"], reverse=True)


def _loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default
