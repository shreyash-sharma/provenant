"""Cline (VS Code) integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from provenant.cli.editor_setup import EditorSetupOptions
from provenant.cli.helpers import get_db_url_for_repo, run_async


class ClineSetup:
    """Writes .clinerules at the repo root."""

    project_file_id = "cline_rules"

    def configure_options(self, console_obj: Any, options: EditorSetupOptions) -> EditorSetupOptions:
        if (
            not options.prompt_for_project_files
            or self.project_file_id in options.disabled_project_files
        ):
            return options
        if not click.confirm("  Generate .clinerules?", default=True):
            return options.with_disabled_project_file(self.project_file_id)
        return options

    def write_project_files(self, console_obj: Any, repo_path: Path, options: EditorSetupOptions) -> None:
        if self.project_file_id not in options.disabled_project_files:
            _write_cline_rules(console_obj, repo_path)

    def register_client(self, console_obj: Any, repo_path: Path) -> None:
        pass

    def refresh_project_files(self, console_obj: Any, repo_path: Path, options: EditorSetupOptions) -> None:
        if self.project_file_id in options.disabled_project_files:
            return
        if not (repo_path / ".clinerules").exists():
            return
        _write_cline_rules(console_obj, repo_path)


def _write_cline_rules(console_obj: Any, repo_path: Path) -> None:
    try:
        with console_obj.status("  Generating .clinerules...", spinner="dots"):
            run_async(_write_cline_async(repo_path))
        console_obj.print("  [green]OK[/green] .clinerules updated")
    except Exception as exc:
        console_obj.print(f"  [yellow].clinerules skipped: {exc}[/yellow]")


async def _write_cline_async(repo_path: Path) -> None:
    from provenant.core.generation.editor_files.rules import ClineRulesGenerator
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
    ClineRulesGenerator().write(repo_path, data)
