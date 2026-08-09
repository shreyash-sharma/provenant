"""Local Provenant usage events for agent-assistance telemetry."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import async_sessionmaker

from provenant.core.persistence.database import get_session
from provenant.core.persistence.models import ProvenantUsageEvent

T = TypeVar("T")


async def record_tool_call(
    session_factory: async_sessionmaker | None,
    *,
    repository_id: str | None,
    tool_name: str,
    query_text: str | None = None,
    target_count: int = 0,
    call: Callable[[], Awaitable[T]],
) -> T:
    """Run a tool call and best-effort persist Provenant activity metadata."""
    started = datetime.now(UTC)
    t0 = time.perf_counter()
    success = True
    error_type: str | None = None
    response: Any = None
    try:
        response = await call()
        return response
    except Exception as exc:
        success = False
        error_type = type(exc).__name__
        raise
    finally:
        finished = datetime.now(UTC)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        await _save_event(
            session_factory,
            repository_id=repository_id,
            tool_name=tool_name,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            query_text=query_text,
            target_count=target_count,
            returned_target_count=_returned_target_count(response),
            estimated_context_tokens=_estimated_tokens(response),
            success=success,
            error_type=error_type,
        )


async def _save_event(
    session_factory: async_sessionmaker | None,
    *,
    repository_id: str | None,
    tool_name: str,
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
    query_text: str | None,
    target_count: int,
    returned_target_count: int,
    estimated_context_tokens: int,
    success: bool,
    error_type: str | None,
) -> None:
    if session_factory is None:
        return
    try:
        async with get_session(session_factory) as session:
            session.add(
                ProvenantUsageEvent(
                    repository_id=repository_id,
                    tool_name=tool_name,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    query_text=query_text,
                    target_count=target_count,
                    returned_target_count=returned_target_count,
                    estimated_context_tokens=estimated_context_tokens,
                    success=success,
                    error_type=error_type,
                    client_name=os.environ.get("PROVENANT_CLIENT_NAME"),
                    raw_json=json.dumps({}),
                )
            )
    except Exception:
        return


def _estimated_tokens(response: Any) -> int:
    if response is None:
        return 0
    try:
        return max(1, len(json.dumps(response, default=str, separators=(",", ":"))) // 4)
    except Exception:
        return 0


def _returned_target_count(response: Any) -> int:
    if not isinstance(response, dict):
        return 0
    targets = response.get("targets")
    if isinstance(targets, dict):
        return len(targets)
    results = response.get("results")
    if isinstance(results, list):
        return len(results)
    citations = response.get("citations")
    if isinstance(citations, list):
        return len(citations)
    modules = response.get("modules")
    if isinstance(modules, list):
        return len(modules)
    return 0
