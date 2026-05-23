"""Editor rule file generators for non-Claude AI coding tools.

Cursor   → .cursorrules
Windsurf → .windsurfrules
Copilot  → .github/copilot-instructions.md
Cline    → .clinerules

All share the same Jinja2 template as CLAUDE.md — the content is identical.
Only the file path and user-facing placeholder text differ.
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseEditorFileGenerator
from .data import EditorFileData


class CursorRulesGenerator(BaseEditorFileGenerator):
    """Generates and maintains .cursorrules at the repo root."""

    filename = ".cursorrules"
    marker_tag = "PROVENANT"
    template_name = "claude_md.j2"
    user_placeholder = (
        "# Cursor Rules\n\n"
        "<!-- Add your custom Cursor instructions below. "
        "Provenant will never modify anything outside the PROVENANT markers. -->\n"
    )


class WindsurfRulesGenerator(BaseEditorFileGenerator):
    """Generates and maintains .windsurfrules at the repo root."""

    filename = ".windsurfrules"
    marker_tag = "PROVENANT"
    template_name = "claude_md.j2"
    user_placeholder = (
        "# Windsurf Rules\n\n"
        "<!-- Add your custom Windsurf instructions below. "
        "Provenant will never modify anything outside the PROVENANT markers. -->\n"
    )


class CopilotInstructionsGenerator(BaseEditorFileGenerator):
    """Generates and maintains .github/copilot-instructions.md."""

    filename = "copilot-instructions.md"
    marker_tag = "PROVENANT"
    template_name = "claude_md.j2"
    user_placeholder = (
        "# GitHub Copilot Instructions\n\n"
        "<!-- Add your custom Copilot instructions below. "
        "Provenant will never modify anything outside the PROVENANT markers. -->\n"
    )

    def write(self, repo_path: Path, data: EditorFileData) -> Path:
        github_dir = repo_path / ".github"
        github_dir.mkdir(parents=True, exist_ok=True)
        return super().write(github_dir, data)

    def render_full(self, repo_path: Path, data: EditorFileData) -> str:
        github_dir = repo_path / ".github"
        return super().render_full(github_dir, data)


class ClineRulesGenerator(BaseEditorFileGenerator):
    """Generates and maintains .clinerules at the repo root."""

    filename = ".clinerules"
    marker_tag = "PROVENANT"
    template_name = "claude_md.j2"
    user_placeholder = (
        "# Cline Rules\n\n"
        "<!-- Add your custom Cline instructions below. "
        "Provenant will never modify anything outside the PROVENANT markers. -->\n"
    )
