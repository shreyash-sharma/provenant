"""provenant CLI - codebase intelligence for developers and AI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.table import Table

from provenant.cli import __version__
from provenant.cli.commands.augment_cmd import augment_command
from provenant.cli.commands.claude_md_cmd import claude_md_command
from provenant.cli.commands.costs_cmd import costs_command
from provenant.cli.commands.dead_code_cmd import dead_code_command
from provenant.cli.commands.decision_cmd import decision_group
from provenant.cli.commands.delete_cmd import delete_command
from provenant.cli.commands.doctor_cmd import doctor_command
from provenant.cli.commands.export_cmd import export_command
from provenant.cli.commands.hook_cmd import hook_group
from provenant.cli.commands.init_cmd import init_command
from provenant.cli.commands.mcp_cmd import mcp_command
from provenant.cli.commands.improve_cmd import improve_command
from provenant.cli.commands.reindex_cmd import reindex_command
from provenant.cli.commands.search_cmd import search_command
from provenant.cli.commands.serve_cmd import serve_command
from provenant.cli.commands.status_cmd import status_command
from provenant.cli.commands.update_cmd import update_command
from provenant.cli.commands.watch_cmd import watch_command
from provenant.cli.commands.workspace_cmd import workspace_group
from provenant.cli.helpers import console, get_provenant_dir, resolve_repo_path, run_async


async def _ask_async(repo_path: Path, question: str) -> dict:
    from provenant.core.persistence import (
        FullTextSearch,
        InMemoryVectorStore,
        create_engine,
        create_session_factory,
        init_db,
        resolve_db_url,
    )
    from provenant.llm.providers.embedding.base import MockEmbedder
    from provenant.server.mcp_server import _state
    from provenant.server.mcp_server.tool_answer import provenant_ask

    engine = create_engine(resolve_db_url(repo_path))
    await init_db(engine)
    session_factory = create_session_factory(engine)

    _state._repo_path = str(repo_path)
    _state._session_factory = session_factory
    _state._fts = FullTextSearch(engine)
    await _state._fts.ensure_index()
    _state._vector_store = InMemoryVectorStore(embedder=MockEmbedder())
    _state._decision_store = InMemoryVectorStore(embedder=MockEmbedder())

    import asyncio

    _state._vector_store_ready = asyncio.Event()
    _state._vector_store_ready.set()
    try:
        return await provenant_ask(question)
    finally:
        await engine.dispose()


def _write_compression_log(repo_path: Path, question: str, result: dict) -> None:
    compression = result.get("compression")
    if not isinstance(compression, dict):
        return
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "question": question,
        "files_before": compression.get("initial_files", 0),
        "files_after": compression.get("final_files", 0),
        "compression_pct": compression.get("compression_pct", 0),
        "pruned_files": compression.get("pruned_files", []),
    }
    log_path = get_provenant_dir(repo_path) / "compression_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


@click.command("ask")
@click.argument("question", nargs=-1, required=True)
@click.option("--path", "repo_path_arg", default=None, help="Repository path.")
def ask_command(question: tuple[str, ...], repo_path_arg: str | None) -> None:
    """Ask a question using the MCP answer tool."""
    repo_path = resolve_repo_path(repo_path_arg)
    question_text = " ".join(question).strip()
    result = run_async(_ask_async(repo_path, question_text))
    _write_compression_log(repo_path, question_text, result)

    answer = result.get("answer") or ""
    if answer:
        console.print(answer)
    elif result.get("note"):
        console.print(result["note"])

    compression = result.get("compression") or {}
    before = compression.get("initial_files", 0)
    after = compression.get("final_files", 0)
    pct = compression.get("compression_pct", 0)
    console.print(f"Compressed: {before} -> {after} files ({pct:.0f}% reduction)")

    pruned = compression.get("pruned_files") or []
    if pruned:
        console.print("Pruned files:")
        for path in pruned:
            console.print(f"- {path}")


@click.command("compression-report")
@click.argument("repo_path", required=False, default=None)
def compression_report_command(repo_path: str | None) -> None:
    """Show compression ratios from .provenant/compression_log.jsonl."""
    root = resolve_repo_path(repo_path)
    log_path = get_provenant_dir(root) / "compression_log.jsonl"
    table = Table(title="Compression Report")
    table.add_column("timestamp")
    table.add_column("question")
    table.add_column("files_before", justify="right")
    table.add_column("files_after", justify="right")
    table.add_column("compression%", justify="right")

    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            question = str(row.get("question", ""))
            if len(question) > 40:
                question = question[:37] + "..."
            table.add_row(
                str(row.get("timestamp", "")),
                question,
                str(row.get("files_before", "")),
                str(row.get("files_after", "")),
                str(row.get("compression_pct", "")),
            )

    console.print(table)


@click.group()
@click.version_option(version=__version__, prog_name="provenant")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """provenant -- codebase intelligence for developers and AI."""
    # Self-heal: migrate any legacy `provenant augment` Claude Code hooks
    # to the import-isolated `provenant-augment` console script. Cheap,
    # silent, idempotent - only writes when there is something to change.
    # Skipped when invoked as the augment subcommand itself (hot path on
    # every Grep/Glob/Bash) - `augment_hook.main` handles that case.
    if ctx.invoked_subcommand != "augment":
        try:
            from provenant.cli.editor_integrations.claude_config import migrate_claude_code_hooks

            migrate_claude_code_hooks()
        except Exception:
            pass


@cli.command("embeddings")
@click.argument("action", type=click.Choice(["clear"]))
@click.option("--model", default="BAAI/bge-small-en-v1.5", show_default=True, help="Model name to clear.")
def embeddings_command(action: str, model: str) -> None:
    """Manage local embedding models.

    \b
    provenant embeddings clear              — delete cached BAAI/bge-small-en-v1.5
    provenant embeddings clear --model NAME — delete a specific cached model
    """
    import shutil

    # fastembed caches models under ~/.cache/fastembed/ using the model name with / replaced by _
    cache_dir = Path.home() / ".cache" / "fastembed"
    slug = model.replace("/", "_")
    target = cache_dir / slug

    if not target.exists():
        # Also try exact name in case fastembed stores it differently
        alt = cache_dir / model
        if alt.exists():
            target = alt
        else:
            console.print(f"  [dim]Nothing to clear — model not found in {cache_dir}[/dim]")
            console.print(f"  [dim]Looked for: {target.name}[/dim]")
            return

    size_mb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / 1_048_576
    shutil.rmtree(target)
    console.print(f"  [green]OK[/green] Deleted {target.name} ({size_mb:.0f} MB)")
    console.print("  [dim]Model will be re-downloaded on next provenant init.[/dim]")


cli.add_command(augment_command)
cli.add_command(init_command)
cli.add_command(delete_command)
cli.add_command(claude_md_command)
cli.add_command(costs_command)
cli.add_command(update_command)
cli.add_command(dead_code_command)
cli.add_command(decision_group)
cli.add_command(search_command)
cli.add_command(ask_command)
cli.add_command(compression_report_command)
cli.add_command(export_command)
cli.add_command(hook_group)
cli.add_command(status_command)
cli.add_command(doctor_command)
cli.add_command(watch_command)
cli.add_command(serve_command)
cli.add_command(mcp_command)
cli.add_command(improve_command)
cli.add_command(reindex_command)
cli.add_command(workspace_group)


if __name__ == "__main__":
    cli()
