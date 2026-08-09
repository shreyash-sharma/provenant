"""Helpers for recording Provenant tool activity."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from provenant.core.persistence.database import get_session
from provenant.core.telemetry.events import record_tool_call
from provenant.server.mcp_server._helpers import _get_repo

T = TypeVar("T")


async def record_provenant_tool_call(
    ctx: Any,
    *,
    tool_name: str,
    query_text: str | None = None,
    target_count: int = 0,
    call: Callable[[], Awaitable[T]],
) -> T:
    repo_id = await _repo_id(ctx)
    return await record_tool_call(
        getattr(ctx, "session_factory", None),
        repository_id=repo_id,
        tool_name=tool_name,
        query_text=query_text,
        target_count=target_count,
        call=call,
    )


async def _repo_id(ctx: Any) -> str | None:
    try:
        async with get_session(ctx.session_factory) as session:
            repo = await _get_repo(session)
            return repo.id
    except Exception:
        return None
