"""Unit tests for HyDE helpers and speculative prefetch helpers.

All tests are dependency-free: no DB, no real LLM, no filesystem state
beyond tmp_path fixtures. Async tests use pytest-asyncio (asyncio_mode=auto
is set in pyproject.toml).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock


# ---------------------------------------------------------------------------
# Helpers: make lightweight fake hit objects for _rrf_merge
# ---------------------------------------------------------------------------

def _hit(page_id: str) -> Any:
    """Minimal fake SearchResult with a page_id attribute."""
    return SimpleNamespace(page_id=page_id)


# ---------------------------------------------------------------------------
# _rrf_merge tests
# ---------------------------------------------------------------------------

def test_rrf_merge_item_in_both_lists_ranks_first():
    """Doc present in both FTS and vector lists should outscore docs in one."""
    from provenant.server.mcp_server.tool_answer import _rrf_merge

    fts   = [_hit("shared"), _hit("fts_only")]
    vec   = [_hit("shared"), _hit("vec_only")]
    result = _rrf_merge(fts, vec, k=60, top_n=3)
    ids = [r.page_id for r in result]
    assert ids[0] == "shared", f"shared should rank first, got {ids}"


def test_rrf_merge_deduplicates():
    """Same page_id appearing in both lists appears exactly once in output."""
    from provenant.server.mcp_server.tool_answer import _rrf_merge

    fts = [_hit("a"), _hit("b")]
    vec = [_hit("a"), _hit("c")]
    result = _rrf_merge(fts, vec, k=60, top_n=10)
    ids = [r.page_id for r in result]
    assert len(ids) == len(set(ids)), "duplicate page_ids in output"
    assert "a" in ids


def test_rrf_merge_top_n_respected():
    """Output is capped at top_n regardless of input size."""
    from provenant.server.mcp_server.tool_answer import _rrf_merge

    fts = [_hit(f"f{i}") for i in range(20)]
    vec = [_hit(f"v{i}") for i in range(20)]
    result = _rrf_merge(fts, vec, k=60, top_n=8)
    assert len(result) <= 8


def test_rrf_merge_empty_inputs():
    """Both lists empty → empty output."""
    from provenant.server.mcp_server.tool_answer import _rrf_merge

    assert _rrf_merge([], [], k=60, top_n=8) == []


def test_rrf_merge_one_empty_list():
    """One empty list → output is just the non-empty list (capped at top_n)."""
    from provenant.server.mcp_server.tool_answer import _rrf_merge

    fts = [_hit("a"), _hit("b"), _hit("c")]
    result = _rrf_merge(fts, [], k=60, top_n=5)
    ids = [r.page_id for r in result]
    assert set(ids) == {"a", "b", "c"}


def test_rrf_merge_fts_canonical_wins_on_overlap():
    """When FTS and vector both have a hit, the FTS object is returned (setdefault)."""
    from provenant.server.mcp_server.tool_answer import _rrf_merge

    fts_obj = _hit("overlap")
    fts_obj.source = "fts"
    vec_obj = _hit("overlap")
    vec_obj.source = "vec"

    result = _rrf_merge([fts_obj], [vec_obj], k=60, top_n=5)
    overlap = next(r for r in result if r.page_id == "overlap")
    assert overlap.source == "fts", "FTS canonical should win via setdefault"


# ---------------------------------------------------------------------------
# _generate_hypothetical_doc tests (async)
# ---------------------------------------------------------------------------

async def test_generate_hypothetical_doc_returns_text_on_success():
    """When provider.generate succeeds, function returns non-empty string."""
    from provenant.server.mcp_server.tool_answer import _generate_hypothetical_doc

    class _FakeResponse:
        content = "src/auth/service.py: handles token validation via validate_token()."

    provider = AsyncMock()
    provider.generate = AsyncMock(return_value=_FakeResponse())

    result = await _generate_hypothetical_doc("how is auth validated?", provider)
    assert isinstance(result, str)
    assert len(result) > 0


async def test_generate_hypothetical_doc_returns_none_on_exception():
    """Provider that raises → function swallows the error and returns None."""
    from provenant.server.mcp_server.tool_answer import _generate_hypothetical_doc

    provider = AsyncMock()
    provider.generate = AsyncMock(side_effect=RuntimeError("network error"))

    result = await _generate_hypothetical_doc("any question", provider)
    assert result is None


async def test_generate_hypothetical_doc_returns_none_on_empty_content():
    """Provider that returns empty string → function returns None."""
    from provenant.server.mcp_server.tool_answer import _generate_hypothetical_doc

    class _EmptyResponse:
        content = "   "

    provider = AsyncMock()
    provider.generate = AsyncMock(return_value=_EmptyResponse())

    result = await _generate_hypothetical_doc("any question", provider)
    assert result is None


# ---------------------------------------------------------------------------
# _extract_paths_from_output tests
# ---------------------------------------------------------------------------

def test_extract_paths_from_output_finds_existing_files(tmp_path: Path):
    """Files that exist on disk are returned; non-existent ones are filtered."""
    from provenant.cli.commands.augment_cmd import _extract_paths_from_output

    # Create a real file in tmp_path so the filter passes
    (tmp_path / "auth.py").write_text("# auth")
    (tmp_path / "utils.py").write_text("# utils")

    output = "auth.py:23: def validate_token()\nutils.py:5: import os\nnonexistent.py:1: foo"
    result = _extract_paths_from_output(output, tmp_path)

    assert "auth.py" in result
    assert "utils.py" in result
    assert "nonexistent.py" not in result


def test_extract_paths_from_output_top_n_by_frequency(tmp_path: Path):
    """Returns at most _PREFETCH_TOP_PATHS paths, highest frequency first."""
    from provenant.cli.commands.augment_cmd import _extract_paths_from_output, _PREFETCH_TOP_PATHS

    # Create files
    for name in ("a.py", "b.py", "c.py", "d.py"):
        (tmp_path / name).write_text("x")

    # a.py appears 5×, b.py 3×, c.py 2×, d.py 1×
    output = "a.py\na.py\na.py\na.py\na.py\nb.py\nb.py\nb.py\nc.py\nc.py\nd.py"
    result = _extract_paths_from_output(output, tmp_path)

    assert len(result) <= _PREFETCH_TOP_PATHS
    if result:
        assert result[0] == "a.py"


def test_extract_paths_from_output_empty_input(tmp_path: Path):
    """Empty output → empty list."""
    from provenant.cli.commands.augment_cmd import _extract_paths_from_output

    assert _extract_paths_from_output("", tmp_path) == []


# ---------------------------------------------------------------------------
# _evict_prefetch_cache tests
# ---------------------------------------------------------------------------

def test_evict_prefetch_cache_drops_expired():
    """Entries older than TTL are removed; fresh entries are kept."""
    from provenant.cli.commands.augment_cmd import _evict_prefetch_cache, _PREFETCH_TTL_SECONDS

    now = time.time()
    entries = {
        "old.py": {"result": {}, "_ts": now - _PREFETCH_TTL_SECONDS - 10},
        "fresh.py": {"result": {}, "_ts": now},
    }
    result = _evict_prefetch_cache(entries)
    assert "old.py" not in result
    assert "fresh.py" in result


def test_evict_prefetch_cache_lru_on_overflow():
    """When >_PREFETCH_MAX_ENTRIES entries exist, oldest are dropped first."""
    from provenant.cli.commands.augment_cmd import _evict_prefetch_cache, _PREFETCH_MAX_ENTRIES

    now = time.time()
    entries = {
        f"file{i}.py": {"result": {}, "_ts": now - (100 - i)}
        for i in range(_PREFETCH_MAX_ENTRIES + 5)
    }
    result = _evict_prefetch_cache(entries)
    assert len(result) <= _PREFETCH_MAX_ENTRIES
    # The 5 oldest (lowest _ts) should be gone
    for i in range(5):
        assert f"file{i}.py" not in result


def test_evict_prefetch_cache_no_eviction_when_under_limit():
    """Under the limit with fresh entries → nothing removed."""
    from provenant.cli.commands.augment_cmd import _evict_prefetch_cache

    now = time.time()
    entries = {f"f{i}.py": {"result": {}, "_ts": now} for i in range(3)}
    result = _evict_prefetch_cache(entries)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# _read_prefetch_cache / _write_prefetch_cache round-trip
# ---------------------------------------------------------------------------

def test_read_write_prefetch_cache_roundtrip(tmp_path: Path):
    """Write entries then read them back — must be identical."""
    from provenant.cli.commands.augment_cmd import _read_prefetch_cache, _write_prefetch_cache

    cache_path = tmp_path / ".prefetch_cache.json"
    entries = {
        "src/auth.py": {"result": {"target": "src/auth.py", "docs": {"summary": "Auth module"}}, "_ts": 1234.0},
        "src/utils.py": {"result": {"target": "src/utils.py", "docs": {"summary": "Utils"}}, "_ts": 5678.0},
    }
    _write_prefetch_cache(cache_path, entries)
    loaded = _read_prefetch_cache(cache_path)
    assert loaded == entries


def test_read_prefetch_cache_returns_empty_on_missing_file(tmp_path: Path):
    """Non-existent cache file → returns empty dict, no exception."""
    from provenant.cli.commands.augment_cmd import _read_prefetch_cache

    result = _read_prefetch_cache(tmp_path / "no_such_file.json")
    assert result == {}


def test_write_prefetch_cache_atomic(tmp_path: Path):
    """After write, no .tmp file lingers."""
    from provenant.cli.commands.augment_cmd import _write_prefetch_cache

    cache_path = tmp_path / ".prefetch_cache.json"
    _write_prefetch_cache(cache_path, {"x.py": {"result": {}, "_ts": 0.0}})

    assert cache_path.exists()
    tmp = cache_path.with_suffix(".tmp")
    assert not tmp.exists(), ".tmp file should not linger after atomic write"
