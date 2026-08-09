"""``provenant usage`` - ingest and report local coding-agent usage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from rich.table import Table

from provenant.cli.helpers import (
    console,
    get_db_url_for_repo,
    resolve_repo_path,
    run_async,
)


@click.group("usage")
def usage_group() -> None:
    """Sync and report agent token/cost usage from ccusage."""


@usage_group.command("sync")
@click.argument("path", required=False, default=None)
@click.option("--since", default=None, help="Start date passed to ccusage, e.g. 20260801.")
@click.option("--until", default=None, help="End date passed to ccusage, e.g. 20260809.")
@click.option("--include-sessions/--no-include-sessions", default=True, show_default=True)
@click.option("--include-blocks", is_flag=True, default=False, help="Also import ccusage blocks.")
@click.option("--use-npx", is_flag=True, default=False, help="Run via npx ccusage if ccusage is not installed globally.")
@click.option("--online", is_flag=True, default=False, help="Allow ccusage to refresh pricing data.")
@click.option("--json", "as_json", is_flag=True, default=False)
def usage_sync_command(
    path: str | None,
    since: str | None,
    until: str | None,
    include_sessions: bool,
    include_blocks: bool,
    use_npx: bool,
    online: bool,
    as_json: bool,
) -> None:
    """Import a ccusage snapshot into the repo-local Provenant database."""
    repo_path = resolve_repo_path(path)
    result = run_async(
        _sync_usage(
            repo_path,
            since=since,
            until=until,
            include_sessions=include_sessions,
            include_blocks=include_blocks,
            use_npx=use_npx,
            offline=not online,
        )
    )
    if as_json:
        import json

        print(json.dumps(result, indent=2))
        return

    console.print(
        f"[green]Synced[/green] {result['row_count']} usage rows "
        f"from {', '.join(result['reports'])}"
    )
    totals = result.get("totals", {})
    console.print(
        f"Tokens: {int(totals.get('total_tokens') or 0):,}  "
        f"Cost: ${float(totals.get('total_cost') or 0.0):.4f}"
    )


@usage_group.command("report")
@click.argument("path", required=False, default=None)
@click.option(
    "--by",
    "group_by",
    type=click.Choice(["day", "project", "agent", "model", "session"]),
    default="day",
    show_default=True,
)
@click.option("--json", "as_json", is_flag=True, default=False)
def usage_report_command(path: str | None, group_by: str, as_json: bool) -> None:
    """Show the latest persisted agent usage snapshot."""
    repo_path = resolve_repo_path(path)
    result = run_async(_read_usage(repo_path))
    if as_json:
        import json

        print(json.dumps(result, indent=2))
        return

    if not result:
        console.print("[yellow]No usage snapshots found. Run 'provenant usage sync' first.[/yellow]")
        return

    snapshot = result["snapshot"]
    totals = snapshot.get("totals", {})
    console.print(
        f"[bold]Agent Usage[/bold]  "
        f"last sync: {snapshot.get('created_at') or '-'}  "
        f"tokens: {int(totals.get('total_tokens') or 0):,}  "
        f"cost: ${float(totals.get('total_cost') or 0.0):.4f}"
    )
    savings = result.get("savings") or {}
    if savings.get("event_count"):
        assisted = savings.get("assisted") or {}
        unassisted = savings.get("unassisted") or {}
        delta = savings.get("observed_delta") or {}
        token_delta = delta.get("avg_token_reduction_pct")
        cost_delta = delta.get("avg_cost_reduction_pct")
        console.print(
            "[bold]Observed Provenant-assisted sessions[/bold]  "
            f"assisted: {int(assisted.get('sessions') or 0)}  "
            f"unassisted: {int(unassisted.get('sessions') or 0)}  "
            f"token delta: {_fmt_pct(token_delta)}  "
            f"cost delta: {_fmt_pct(cost_delta)}"
        )

    group_key = "daily" if group_by == "day" else group_by
    rows = result.get("groups", {}).get(group_key, [])
    table = Table(title=f"Usage by {group_by}")
    table.add_column(group_by.capitalize(), style="cyan")
    table.add_column("Rows", justify="right")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Cache", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Cost", justify="right")

    for row in rows:
        cache_tokens = int(row.get("cache_creation_tokens") or 0) + int(row.get("cache_read_tokens") or 0)
        table.add_row(
            str(row.get("key") or "unknown"),
            str(row.get("rows") or 0),
            f"{int(row.get('input_tokens') or 0):,}",
            f"{int(row.get('output_tokens') or 0):,}",
            f"{cache_tokens:,}",
            f"{int(row.get('total_tokens') or 0):,}",
            f"${float(row.get('total_cost') or 0.0):.4f}",
        )

    console.print(table)


async def _sync_usage(
    repo_path: Path,
    *,
    since: str | None,
    until: str | None,
    include_sessions: bool,
    include_blocks: bool,
    use_npx: bool,
    offline: bool,
) -> dict[str, Any]:
    from provenant.core.persistence import (
        create_engine,
        create_session_factory,
        get_session,
        init_db,
    )
    from provenant.core.persistence.crud import get_repository_by_path
    from provenant.core.telemetry.adapters.ccusage import collect_ccusage
    from provenant.core.telemetry.usage import save_usage_snapshot

    engine = create_engine(get_db_url_for_repo(repo_path))
    await init_db(engine)
    session_factory = create_session_factory(engine)

    try:
        async with get_session(session_factory) as session:
            repo = await get_repository_by_path(session, str(repo_path))
            repo_id = repo.id if repo else None

        snapshot = collect_ccusage(
            since=since,
            until=until,
            include_sessions=include_sessions,
            include_blocks=include_blocks,
            use_npx=use_npx,
            offline=offline,
        )
        return await save_usage_snapshot(session_factory, snapshot, repository_id=repo_id)
    finally:
        await engine.dispose()


async def _read_usage(repo_path: Path) -> dict[str, Any] | None:
    from provenant.core.persistence import (
        create_engine,
        create_session_factory,
        get_session,
        init_db,
    )
    from provenant.core.persistence.crud import get_repository_by_path
    from provenant.core.telemetry.usage import latest_usage_snapshot

    engine = create_engine(get_db_url_for_repo(repo_path))
    await init_db(engine)
    session_factory = create_session_factory(engine)

    try:
        async with get_session(session_factory) as session:
            repo = await get_repository_by_path(session, str(repo_path))
            repo_id = repo.id if repo else None
        return await latest_usage_snapshot(session_factory, repository_id=repo_id)
    finally:
        await engine.dispose()


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "-"
