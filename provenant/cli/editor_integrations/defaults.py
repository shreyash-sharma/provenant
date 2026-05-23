"""Default editor setup integration registry."""

from __future__ import annotations

from provenant.cli.editor_setup import EditorSetupIntegration

from .claude import ClaudeCodeSetup
from .cursor import CursorSetup
from .windsurf import WindsurfSetup
from .copilot import CopilotSetup
from .cline import ClineSetup


def get_default_editor_integrations() -> tuple[EditorSetupIntegration, ...]:
    """Return the editor integrations enabled by default."""

    return (
        ClaudeCodeSetup(),
        CursorSetup(),
        WindsurfSetup(),
        CopilotSetup(),
        ClineSetup(),
    )


def get_default_disabled_project_files(*, no_claude_md: bool = False) -> tuple[str, ...]:
    """Map legacy CLI editor-file flags to integration-owned project file ids."""

    disabled: list[str] = []
    if no_claude_md:
        disabled.append(ClaudeCodeSetup.project_file_id)
    return tuple(disabled)
