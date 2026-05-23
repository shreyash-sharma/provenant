"""Editor-file generators for provenant.

Provides generators that create and maintain AI-editor configuration files
(CLAUDE.md, cursor.md, etc.) from already-indexed codebase data.

No LLM calls are made — all content is derived from the provenant DB.
"""

from .claude_md import ClaudeMdGenerator, WorkspaceClaudeMdGenerator
from .rules import (
    CursorRulesGenerator,
    WindsurfRulesGenerator,
    CopilotInstructionsGenerator,
    ClineRulesGenerator,
)
from .data import (
    DecisionSummary,
    EditorFileData,
    HotspotFile,
    KeyModule,
    TechStackItem,
    WorkspaceEditorFileData,
    WorkspaceRepoSummary,
)
from .fetcher import EditorFileDataFetcher

__all__ = [
    # Generators
    "ClaudeMdGenerator",
    "WorkspaceClaudeMdGenerator",
    "CursorRulesGenerator",
    "WindsurfRulesGenerator",
    "CopilotInstructionsGenerator",
    "ClineRulesGenerator",
    # Data containers
    "DecisionSummary",
    "EditorFileData",
    "HotspotFile",
    "KeyModule",
    "TechStackItem",
    "WorkspaceEditorFileData",
    "WorkspaceRepoSummary",
    # Fetcher
    "EditorFileDataFetcher",
]
