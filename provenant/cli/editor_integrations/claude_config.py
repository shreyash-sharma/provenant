"""Claude Desktop and Claude Code MCP config helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from provenant.cli.mcp_config import (
    generate_mcp_config,
    load_existing_config,
    merge_mcp_entry,
)


def _claude_desktop_config_path() -> Path | None:
    """Return the Claude Desktop config path for this OS, or None if unsupported."""
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    if sys.platform == "win32":
        appdata = Path.home() / "AppData" / "Roaming"
        return appdata / "Claude" / "claude_desktop_config.json"
    # Linux / other: Claude Desktop not officially supported yet
    return None


def _claude_code_settings_path() -> Path:
    """Return the global Claude Code settings path (~/.claude/settings.json)."""
    return Path.home() / ".claude" / "settings.json"


def register_with_claude_desktop(repo_path: Path) -> Path | None:
    """Add provenant MCP server to Claude Desktop's config.

    Returns the config path if successful, None if Claude Desktop is not
    present or the platform is unsupported.
    """
    config_path = _claude_desktop_config_path()
    if config_path is None:
        return None
    if not config_path.parent.exists():
        # Claude Desktop not installed
        return None
    entry = generate_mcp_config(repo_path)["mcpServers"]
    return config_path if merge_mcp_entry(config_path, entry) else None


def register_with_claude_code(repo_path: Path) -> Path | None:
    """Add provenant MCP server to global Claude Code settings (~/.claude/settings.json).

    Returns the settings path if successful, None on failure.
    """
    settings_path = _claude_code_settings_path()
    entry = generate_mcp_config(repo_path)["mcpServers"]
    return settings_path if merge_mcp_entry(settings_path, entry) else None


def install_claude_code_hooks() -> Path | None:
    """Register PreToolUse + PostToolUse hooks in ~/.claude/settings.json.

    PreToolUse: injects a Provenant reminder before Read/Glob/Grep so Claude
    is nudged to call get_context() first.
    PostToolUse: enriches Grep/Glob results with codebase context.
    Existing user hooks are preserved.
    """
    settings_path = _claude_code_settings_path()

    pre_hook_entry = {
        "matcher": "Read|Glob|Grep",
        "hooks": [
            {
                "type": "command",
                "command": "provenant-augment",
                "timeout": 5,
                "statusMessage": "Provenant: call get_context() before reading source files",
            }
        ],
    }

    post_hook_entry = {
        "matcher": "Bash|Grep|Glob",
        "hooks": [
            {
                "type": "command",
                "command": "provenant-augment",
                "timeout": 10,
                "statusMessage": "Checking codebase context...",
            }
        ],
    }

    try:
        if settings_path.exists():
            existing = load_existing_config(settings_path)
        else:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            existing = {}

        hooks = existing.setdefault("hooks", {})

        # PreToolUse: remind Claude to use get_context() before Read/Glob/Grep.
        pre_hooks = hooks.setdefault("PreToolUse", [])
        _strip_provenant_pretool(pre_hooks)
        pre_hooks.append(pre_hook_entry)

        # PostToolUse: migrate legacy command + matcher, then add if missing.
        post_hooks = hooks.setdefault("PostToolUse", [])
        _migrate_legacy_hook(post_hooks)
        if not _has_provenant_hook(post_hooks):
            post_hooks.append(post_hook_entry)

        settings_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        return settings_path
    except OSError:
        return None


def _has_provenant_hook(hook_list: list) -> bool:
    """Check if a provenant hook is already registered, current or legacy."""
    for entry in hook_list:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if (
                "provenant-augment" in cmd
                or "provenant augment" in cmd
                or "stratum-augment" in cmd
                or "stratum augment" in cmd
            ):
                return True
    return False


def _is_provenant_hook(hook: dict) -> bool:
    cmd = hook.get("command", "")
    return (
        "provenant-augment" in cmd
        or "provenant augment" in cmd
        or "stratum-augment" in cmd
        or "stratum augment" in cmd
    )


def _strip_provenant_pretool(hook_list: list) -> bool:
    """Remove provenant's PreToolUse entry from a hook bucket in place."""
    changed = False
    for entry in list(hook_list):
        kept = [h for h in entry.get("hooks", []) if not _is_provenant_hook(h)]
        if len(kept) != len(entry.get("hooks", [])):
            changed = True
            if kept:
                entry["hooks"] = kept
            else:
                hook_list.remove(entry)
    return changed


def _migrate_legacy_hook(hook_list: list) -> bool:
    """In-place migration of legacy PostToolUse entries to current shape.

    Upgrades old ``stratum augment``, ``stratum-augment``, and the transitional
    ``provenant augment`` (space form) to the current ``provenant-augment`` command.
    """
    changed = False
    for entry in hook_list:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if cmd in ("stratum augment", "stratum-augment", "provenant augment"):
                hook["command"] = "provenant-augment"
                changed = True
        matcher = entry.get("matcher", "")
        only_provenant = entry.get("hooks") and all(
            _is_provenant_hook(h) for h in entry["hooks"]
        )
        if only_provenant and matcher == "Bash":
            entry["matcher"] = "Bash|Grep|Glob"
            changed = True
    return changed


def migrate_claude_code_hooks() -> bool:
    """Self-healing migration of legacy Claude Code hook entries."""
    settings_path = _claude_code_settings_path()
    if not settings_path.exists():
        return False

    try:
        existing = load_existing_config(settings_path)
    except Exception:
        return False

    hooks = existing.get("hooks")
    if not isinstance(hooks, dict):
        return False

    changed = False

    pre = hooks.get("PreToolUse")
    if isinstance(pre, list) and _strip_provenant_pretool(pre):
        changed = True
        if not pre:
            hooks.pop("PreToolUse", None)

    post = hooks.get("PostToolUse")
    if isinstance(post, list) and _migrate_legacy_hook(post):
        changed = True

    if not changed:
        return False

    try:
        settings_path.write_text(
            json.dumps(existing, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        return False
    return True
