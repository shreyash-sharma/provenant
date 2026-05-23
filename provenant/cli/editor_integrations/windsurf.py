"""Windsurf editor integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from provenant.cli.editor_setup import EditorSetupOptions
from provenant.cli.helpers import get_db_url_for_repo, run_async
from provenant.cli.mcp_config import generate_mcp_config


class WindsurfSetup:
    """Writes .windsurfrules and the Windsurf MCP config."""

    project_file_id = "windsurf_rules"

    # Windsurf global MCP config location
    _GLOBAL_MCP = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"

    def configure_options(self, console_obj: Any, options: EditorSetupOptions) -> EditorSetupOptions:
        if (
            not options.prompt_for_project_files
            or self.project_file_id in options.disabled_project_files
        ):
            return options
        if not click.confirm("  Generate .windsurfrules?", default=True):
            return options.with_disabled_project_file(self.project_file_id)
        return options

    def write_project_files(self, console_obj: Any, repo_path: Path, options: EditorSetupOptions) -> None:
        _write_windsurf_mcp(repo_path, self._GLOBAL_MCP)
        if self.project_file_id not in options.disabled_project_files:
            _write_windsurf_rules(console_obj, repo_path)

    def register_client(self, console_obj: Any, repo_path: Path) -> None:
        pass

    def refresh_project_files(self, console_obj: Any, repo_path: Path, options: EditorSetupOptions) -> None:
        if self.project_file_id in options.disabled_project_files:
            return
        if not (repo_path / ".windsurfrules").exists():
            return
        _write_windsurf_rules(console_obj, repo_path)


def _write_windsurf_mcp(repo_path: Path, global_config: Path) -> None:
    """Merge Provenant into Windsurf's global MCP config."""
    mcp = generate_mcp_config(repo_path)
    global_config.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if global_config.exists():
        try:
            existing = json.loads(global_config.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    servers = dict(existing.get("mcpServers", {}))
    servers.update(mcp["mcpServers"])
    existing["mcpServers"] = servers
    global_config.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def _write_windsurf_rules(console_obj: Any, repo_path: Path) -> None:
    try:
        with console_obj.status("  Generating .windsurfrules...", spinner="dots"):
            run_async(_write_windsurf_rules_async(repo_path))
        console_obj.print("  [green]OK[/green] .windsurfrules updated")
    except Exception as exc:
        console_obj.print(f"  [yellow].windsurfrules skipped: {exc}[/yellow]")


async def _write_windsurf_rules_async(repo_path: Path) -> None:
    from provenant.core.generation.editor_files.rules import WindsurfRulesGenerator
    from provenant.core.generation.editor_files import EditorFileDataFetcher
    from provenant.core.persistence import (
        create_engine, create_session_factory, get_session, init_db,
    )
    from provenant.core.persistence.crud import get_repository_by_path

    url = get_db_url_for_repo(repo_path)
    engine = create_engine(url)
    await init_db(engine)
    sf = create_session_factory(engine)
    try:
        async with get_session(sf) as session:
            repo = await get_repository_by_path(session, str(repo_path))
            if repo is None:
                return
            fetcher = EditorFileDataFetcher(session, repo.id, repo_path)
            data = await fetcher.fetch()
    finally:
        await engine.dispose()
    WindsurfRulesGenerator().write(repo_path, data)
