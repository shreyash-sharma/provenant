"""Provenant HTTP API - FastAPI app factory.

Wraps MCP tool functions as REST endpoints so the Next.js frontend can call
them without running an MCP transport.

Start with:
    uvicorn "provenant.server.app:create_app" --factory --port 7337
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

_WEB_CACHE_DIR = Path.home() / ".provenant" / "web"


async def _init_state(repo_path: str) -> None:
    """Initialize the same process-global state used by the MCP tools."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from provenant.core.persistence.database import init_db, resolve_db_url
    from provenant.core.persistence.search import FullTextSearch
    from provenant.core.persistence.vector_store import InMemoryVectorStore
    from provenant.llm.providers.embedding.base import MockEmbedder
    from provenant.server.mcp_server import _state

    db_url = resolve_db_url(repo_path)
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_async_engine(db_url, connect_args=connect_args)
    await init_db(engine)

    fts = FullTextSearch(engine)
    await fts.ensure_index()

    ready = asyncio.Event()
    ready.set()

    _state._repo_path = repo_path
    _state._session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    _state._fts = fts
    _state._vector_store = InMemoryVectorStore(embedder=MockEmbedder())
    _state._decision_store = InMemoryVectorStore(embedder=MockEmbedder())
    _state._vector_store_ready = ready


@asynccontextmanager
async def _lifespan(app: FastAPI):
    repo_path = os.environ.get("PROVENANT_REPO_PATH", ".")
    await _init_state(repo_path)
    yield


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    compress: bool = False
    force_synthesize: bool = True


class ContextRequest(BaseModel):
    targets: list[str]
    include: list[str] | None = None
    compact: bool = True


class RiskRequest(BaseModel):
    targets: list[str]
    changed_files: list[str] | None = None


class DeadCodeRequest(BaseModel):
    kind: str | None = None
    min_confidence: float = 0.7
    safe_only: bool = False
    group_by: str | None = "directory"


class RepairRunRequest(BaseModel):
    dry_run: bool = False
    top_n: int = Field(10, ge=1, le=100)
    weak_threshold: float = Field(0.25, ge=0.0, le=1.0)
    min_retrievals: int = Field(3, ge=1)
    selected_pages: list[str] | None = None  # if set, repair only these specific pages


def _as_http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=str(exc))


def create_app() -> FastAPI:
    app = FastAPI(title="Provenant API", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/project")
    async def project() -> dict[str, Any]:
        from sqlalchemy import func, select

        from provenant.core.persistence.database import get_session
        from provenant.core.persistence.models import GraphNode, Page
        from provenant.server.mcp_server import _state
        from provenant.server.mcp_server._helpers import _get_repo

        try:
            async with get_session(_state._session_factory) as session:
                repo = await _get_repo(session)
                pages = await session.scalar(
                    select(func.count()).select_from(Page).where(Page.repository_id == repo.id)
                )
                files = await session.scalar(
                    select(func.count())
                    .select_from(GraphNode)
                    .where(GraphNode.repository_id == repo.id, GraphNode.node_type == "file")
                )
                symbols = await session.scalar(
                    select(func.count())
                    .select_from(GraphNode)
                    .where(GraphNode.repository_id == repo.id, GraphNode.node_type == "symbol")
                )
                settings = json.loads(repo.settings_json or "{}")

            state: dict[str, Any] = {}
            repo_path = _state._repo_path or repo.local_path
            state_path = os.path.join(repo_path, ".provenant", "state.json")
            if os.path.exists(state_path):
                with open(state_path, encoding="utf-8") as fh:
                    state = json.load(fh)

            return {
                "id": repo.id,
                "name": repo.name,
                "path": repo.local_path,
                "default_branch": repo.default_branch,
                "head_commit": repo.head_commit,
                "settings": settings,
                "state": state,
                "counts": {
                    "pages": pages or 0,
                    "files": files or 0,
                    "symbols": symbols or 0,
                },
            }
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.get("/api/graph")
    async def graph(limit: int = Query(250, ge=1, le=1000)) -> dict[str, Any]:
        from sqlalchemy import select

        from provenant.core.persistence.database import get_session
        from provenant.core.persistence.models import GraphEdge, GraphNode
        from provenant.server.mcp_server import _state
        from provenant.server.mcp_server._helpers import _get_repo

        try:
            async with get_session(_state._session_factory) as session:
                repo = await _get_repo(session)
                node_rows = await session.execute(
                    select(GraphNode)
                    .where(GraphNode.repository_id == repo.id)
                    .order_by(GraphNode.pagerank.desc())
                    .limit(limit)
                )
                nodes = list(node_rows.scalars().all())
                node_ids = {node.node_id for node in nodes}
                edge_rows = await session.execute(
                    select(GraphEdge)
                    .where(
                        GraphEdge.repository_id == repo.id,
                        GraphEdge.source_node_id.in_(node_ids),
                        GraphEdge.target_node_id.in_(node_ids),
                    )
                    .limit(limit * 3)
                )
                edges = list(edge_rows.scalars().all())

            return {
                "nodes": [
                    {
                        "id": node.node_id,
                        "name": node.name or node.node_id.rsplit("/", 1)[-1],
                        "type": "SYMBOL" if node.node_type == "symbol" else "FILE",
                        "path": node.file_path or node.node_id,
                        "pagerank": node.pagerank,
                        "community_id": node.community_id,
                        "is_entry_point": node.is_entry_point,
                        "symbol_count": node.symbol_count,
                    }
                    for node in nodes
                ],
                "edges": [
                    {
                        "source": edge.source_node_id,
                        "target": edge.target_node_id,
                        "type": edge.edge_type,
                        "confidence": edge.confidence,
                    }
                    for edge in edges
                ],
            }
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.get("/api/overview")
    async def overview() -> dict:
        from provenant.server.mcp_server.tool_overview import provenant_overview

        try:
            return await provenant_overview()
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.post("/api/ask")
    async def ask(body: AskRequest) -> dict:
        from provenant.server.mcp_server.tool_answer import provenant_ask

        try:
            return await provenant_ask(question=body.question)
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.get("/api/search")
    async def search(
        q: str = Query(..., description="Search query"),
        limit: int = Query(10, ge=1, le=50),
        page_type: str | None = Query(None),
    ) -> dict:
        from provenant.server.mcp_server.tool_search import provenant_search

        try:
            return await provenant_search(query=q, limit=limit, page_type=page_type)
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.post("/api/context")
    async def context(body: ContextRequest) -> dict:
        from provenant.server.mcp_server.tool_context import provenant_context

        try:
            return await provenant_context(
                targets=body.targets,
                include=body.include,
                compact=body.compact,
            )
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.post("/api/risk")
    async def risk(body: RiskRequest) -> dict:
        from provenant.server.mcp_server.tool_risk import provenant_risk

        try:
            return await provenant_risk(targets=body.targets, changed_files=body.changed_files)
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.get("/api/risk/overview")
    async def risk_overview() -> dict[str, list[dict[str, Any]]]:
        from sqlalchemy import select

        from provenant.core.persistence.database import get_session
        from provenant.core.persistence.models import Page
        from provenant.server.mcp_server import _state
        from provenant.server.mcp_server._helpers import _get_repo

        try:
            async with get_session(_state._session_factory) as session:
                repo = await _get_repo(session)
                res = await session.execute(
                    select(Page.target_path, Page.page_type, Page.metadata_json)
                    .where(Page.repository_id == repo.id, Page.page_type == "file_page")
                    .limit(200)
                )
                files = [
                    {"path": row[0], "page_type": row[1], "meta": row[2]}
                    for row in res.all()
                    if row[0]
                ]
            return {"files": files}
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.post("/api/dead-code")
    async def dead_code(body: DeadCodeRequest) -> dict:
        from provenant.server.mcp_server.tool_dead_code import provenant_dead_code

        try:
            return await provenant_dead_code(
                kind=body.kind,
                min_confidence=body.min_confidence,
                safe_only=body.safe_only,
                group_by=body.group_by,
            )
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.get("/api/why")
    async def why(
        query: str | None = Query(None),
        target: str | None = Query(None),
    ) -> dict:
        from provenant.server.mcp_server.tool_why import provenant_why

        try:
            targets = [target] if target else None
            return await provenant_why(query=query or target, targets=targets)
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    # ── Representation model ─────────────────────────────────────────────────

    @app.get("/api/model")
    async def model_snapshot() -> dict[str, Any]:
        """Full representation state: corpus, quality, economics, repair summary."""
        from collections import defaultdict

        from sqlalchemy import func, select

        from provenant.core.persistence.database import get_session
        from provenant.core.persistence.models import GraphEdge, GraphNode, Page
        from provenant.server.mcp_server import _state
        from provenant.server.mcp_server._helpers import _get_repo

        try:
            async with get_session(_state._session_factory) as session:
                repo = await _get_repo(session)
                rid = repo.id

                page_count = await session.scalar(
                    select(func.count()).select_from(Page).where(Page.repository_id == rid)
                )
                file_count = await session.scalar(
                    select(func.count())
                    .select_from(GraphNode)
                    .where(GraphNode.repository_id == rid, GraphNode.node_type == "file")
                )
                symbol_count = await session.scalar(
                    select(func.count())
                    .select_from(GraphNode)
                    .where(GraphNode.repository_id == rid, GraphNode.node_type == "symbol")
                )
                node_count = await session.scalar(
                    select(func.count())
                    .select_from(GraphNode)
                    .where(GraphNode.repository_id == rid)
                )
                edge_count = await session.scalar(
                    select(func.count())
                    .select_from(GraphEdge)
                    .where(GraphEdge.repository_id == rid)
                )

                # Token totals across all pages
                token_rows = await session.execute(
                    select(
                        func.sum(Page.input_tokens),
                        func.sum(Page.output_tokens),
                        func.avg(Page.confidence),
                    ).where(Page.repository_id == rid)
                )
                tok_in, tok_out, avg_conf = token_rows.one()

                # Freshness breakdown
                fresh_rows = await session.execute(
                    select(Page.freshness_status, func.count())
                    .where(Page.repository_id == rid)
                    .group_by(Page.freshness_status)
                )
                freshness: dict[str, int] = {row[0]: row[1] for row in fresh_rows.all()}

                settings = json.loads(repo.settings_json or "{}")

            # state.json — build/index timing and settings
            repo_path = _state._repo_path or repo.local_path
            state: dict[str, Any] = {}
            state_path = os.path.join(repo_path, ".provenant", "state.json")
            if os.path.exists(state_path):
                with open(state_path, encoding="utf-8") as fh:
                    state = json.load(fh)

            # Confidence log summary — repair state and query metrics
            from provenant.cli.commands.improve_cmd import analyze_confidence_log

            log_data = analyze_confidence_log(repo_path)
            records = log_data.get("records", [])
            page_stats = log_data.get("page_stats", {})

            conf_scores = [r.get("confidence_score", 0) for r in records if "confidence_score" in r]
            avg_query_conf = round(sum(conf_scores) / len(conf_scores), 3) if conf_scores else None
            low_conf_count = sum(1 for s in conf_scores if s < 0.35)

            # Weak pages (retrieved ≥3x, citation rate < 25%)
            _MIN_R, _WEAK_T = 3, 0.25
            weak_pages = [
                {
                    "page": p,
                    "retrieved": st["retrieved"],
                    "cited": st["cited"],
                    "citation_rate": round(st["cited"] / st["retrieved"], 3),
                }
                for p, st in page_stats.items()
                if st["retrieved"] >= _MIN_R and (st["cited"] / st["retrieved"]) < _WEAK_T
            ]
            weak_pages.sort(key=lambda x: x["citation_rate"])

            # Repair history from log
            repair_events = [r for r in log_data.get("records", []) if r.get("event") == "repair"]
            # Re-read raw lines to get repair events (analyze_confidence_log skips them)
            from pathlib import Path as _Path
            log_path = _Path(repo_path) / ".provenant" / "confidence_log.jsonl"
            repair_events = []
            if log_path.exists():
                with open(log_path, encoding="utf-8") as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                            if rec.get("event") == "repair":
                                repair_events.append(rec)
                        except json.JSONDecodeError:
                            pass
            last_repair = repair_events[-1] if repair_events else None

            return {
                "repo": {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.local_path,
                    "branch": repo.default_branch,
                    "head_commit": repo.head_commit,
                },
                "settings": settings,
                "state": state,
                "corpus": {
                    "pages": page_count or 0,
                    "files": file_count or 0,
                    "symbols": symbol_count or 0,
                    "graph_nodes": node_count or 0,
                    "graph_edges": edge_count or 0,
                    "build_input_tokens": tok_in or 0,
                    "build_output_tokens": tok_out or 0,
                    "avg_confidence": round(avg_conf, 3) if avg_conf else None,
                    "freshness": freshness,
                },
                "quality": {
                    "avg_attribution_confidence": avg_query_conf,
                    "total_queries": len(conf_scores),
                    "low_confidence_queries": low_conf_count,
                },
                "repair": {
                    "weak_page_count": len(weak_pages),
                    "total_repair_runs": len(repair_events),
                    "last_repair_at": last_repair.get("ts") if last_repair else None,
                    "last_repair_page_count": len(last_repair.get("pages_repaired", [])) if last_repair else 0,
                    "weak_pages": weak_pages[:10],  # top 10 worst for the overview
                },
            }
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    # ── Wiki pages ───────────────────────────────────────────────────────────

    @app.get("/api/pages")
    async def pages(
        page_type: str | None = Query(None),
        freshness: str | None = Query(None),
        limit: int = Query(500, ge=1, le=2000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """List all wiki pages with lightweight metadata (no full content)."""
        from sqlalchemy import select

        from provenant.core.persistence.database import get_session
        from provenant.core.persistence.models import Page
        from provenant.server.mcp_server import _state
        from provenant.server.mcp_server._helpers import _get_repo

        try:
            async with get_session(_state._session_factory) as session:
                repo = await _get_repo(session)

                q = select(
                    Page.id,
                    Page.page_type,
                    Page.title,
                    Page.target_path,
                    Page.summary,
                    Page.confidence,
                    Page.freshness_status,
                    Page.source_hash,
                    Page.version,
                    Page.input_tokens,
                    Page.output_tokens,
                    Page.model_name,
                    Page.provider_name,
                    Page.created_at,
                    Page.updated_at,
                ).where(Page.repository_id == repo.id)

                if page_type:
                    q = q.where(Page.page_type == page_type)
                if freshness:
                    q = q.where(Page.freshness_status == freshness)

                q = q.order_by(Page.confidence.asc(), Page.updated_at.desc())
                q = q.offset(offset).limit(limit)

                rows = await session.execute(q)
                result = rows.all()

            return {
                "pages": [
                    {
                        "id": row.id,
                        "page_type": row.page_type,
                        "title": row.title,
                        "target_path": row.target_path,
                        "summary": row.summary,
                        "confidence": row.confidence,
                        "freshness_status": row.freshness_status,
                        "source_hash": row.source_hash,
                        "version": row.version,
                        "input_tokens": row.input_tokens,
                        "output_tokens": row.output_tokens,
                        "model_name": row.model_name,
                        "provider_name": row.provider_name,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                    for row in result
                ],
                "total": len(result),
                "offset": offset,
                "limit": limit,
            }
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.get("/api/pages/{page_id:path}")
    async def page_detail(page_id: str) -> dict[str, Any]:
        """Full page content + metadata for a single page."""
        from sqlalchemy import select

        from provenant.core.persistence.database import get_session
        from provenant.core.persistence.models import Page, PageVersion
        from provenant.server.mcp_server import _state

        try:
            async with get_session(_state._session_factory) as session:
                result = await session.execute(
                    select(Page).where(Page.id == page_id)
                )
                page = result.scalars().first()
                if not page:
                    raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

                versions = await session.execute(
                    select(
                        PageVersion.version,
                        PageVersion.created_at,
                        PageVersion.model_name,
                    )
                    .where(PageVersion.page_id == page_id)
                    .order_by(PageVersion.version.desc())
                    .limit(10)
                )
                version_rows = versions.all()

            meta = json.loads(page.metadata_json or "{}")
            return {
                "id": page.id,
                "page_type": page.page_type,
                "title": page.title,
                "target_path": page.target_path,
                "summary": page.summary,
                "content": page.content,
                "confidence": page.confidence,
                "freshness_status": page.freshness_status,
                "source_hash": page.source_hash,
                "version": page.version,
                "input_tokens": page.input_tokens,
                "output_tokens": page.output_tokens,
                "model_name": page.model_name,
                "provider_name": page.provider_name,
                "metadata": meta,
                "human_notes": page.human_notes,
                "created_at": page.created_at.isoformat() if page.created_at else None,
                "updated_at": page.updated_at.isoformat() if page.updated_at else None,
                "version_history": [
                    {
                        "version": v.version,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                        "model_name": v.model_name,
                    }
                    for v in version_rows
                ],
            }
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    # ── Repair ───────────────────────────────────────────────────────────────

    @app.get("/api/repair/candidates")
    async def repair_candidates(
        weak_threshold: float = Query(0.25, ge=0.0, le=1.0),
        min_retrievals: int = Query(3, ge=1),
        top_n: int = Query(50, ge=1, le=500),
    ) -> dict[str, Any]:
        """Return weak wiki pages ranked by citation rate, with query-level summary."""
        from pathlib import Path as _Path

        from provenant.cli.commands.improve_cmd import analyze_confidence_log
        from provenant.server.mcp_server import _state

        try:
            repo_path = _Path(_state._repo_path or ".")
            log_data = analyze_confidence_log(repo_path)
            records = log_data.get("records", [])
            page_stats = log_data.get("page_stats", {})

            # Rank pages by citation rate
            candidates = []
            for page, stats in page_stats.items():
                n = stats["retrieved"]
                if n < min_retrievals:
                    continue
                rate = stats["cited"] / n
                if rate < weak_threshold:
                    candidates.append({
                        "page": page,
                        "retrieved": n,
                        "cited": stats["cited"],
                        "citation_rate": round(rate, 3),
                        "status": "weak" if rate < 0.1 else "low",
                    })

            candidates.sort(key=lambda x: (x["citation_rate"], -x["retrieved"]))
            candidates = candidates[:top_n]

            # Affected queries per weak page
            affected: dict[str, list[str]] = {}
            for rec in records:
                retrieved = rec.get("retrieved", [])
                citations = {p.lower() for p in rec.get("citations", [])}
                query = rec.get("question", "")[:120]
                for page_path in retrieved:
                    key = page_path.lower()
                    if key in {c["page"] for c in candidates} and key not in citations:
                        affected.setdefault(key, [])
                        if query and query not in affected[key]:
                            affected[key].append(query)

            for c in candidates:
                c["affected_queries"] = affected.get(c["page"], [])[:5]

            # Summary
            conf_scores = [r.get("confidence_score", 0) for r in records if "confidence_score" in r]

            return {
                "candidates": candidates,
                "summary": {
                    "total_queries": len(conf_scores),
                    "total_pages_tracked": len(page_stats),
                    "weak_page_count": len(candidates),
                    "avg_confidence": round(sum(conf_scores) / len(conf_scores), 3) if conf_scores else None,
                    "low_confidence_queries": sum(1 for s in conf_scores if s < 0.35),
                },
                "params": {
                    "weak_threshold": weak_threshold,
                    "min_retrievals": min_retrievals,
                },
            }
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    @app.post("/api/repair/run")
    async def repair_run(body: RepairRunRequest) -> dict[str, Any]:
        """Trigger attribution-guided repair of weak wiki pages.

        If dry_run=True, returns candidates without regenerating.
        If selected_pages is set, repairs only those pages (ignores weak_threshold).
        Otherwise finds weak pages automatically and repairs top_n.
        """
        import asyncio
        from pathlib import Path as _Path

        from provenant.cli.commands.improve_cmd import _regenerate_pages, analyze_confidence_log
        from provenant.server.mcp_server import _state

        try:
            repo_path = _Path(_state._repo_path or ".")
            log_data = analyze_confidence_log(repo_path)
            page_stats = log_data.get("page_stats", {})

            # Determine which pages to repair
            if body.selected_pages:
                target_pages = body.selected_pages
            else:
                candidates = [
                    (p, st["cited"] / st["retrieved"], st["retrieved"])
                    for p, st in page_stats.items()
                    if st["retrieved"] >= body.min_retrievals
                    and (st["cited"] / st["retrieved"]) < body.weak_threshold
                ]
                candidates.sort(key=lambda x: (x[1], -x[2]))
                target_pages = [p for p, _, _ in candidates[: body.top_n]]

            if not target_pages:
                return {
                    "dry_run": body.dry_run,
                    "pages_targeted": [],
                    "repaired": 0,
                    "failed": 0,
                    "message": "No weak pages found matching criteria.",
                }

            if body.dry_run:
                return {
                    "dry_run": True,
                    "pages_targeted": target_pages,
                    "repaired": 0,
                    "failed": 0,
                    "message": f"Dry run: would repair {len(target_pages)} pages.",
                }

            # Run repair — _regenerate_pages is async and handles its own DB session
            await _regenerate_pages(repo_path, target_pages, page_stats=page_stats)

            # Append repair record to confidence log
            import time

            log_path = repo_path / ".provenant" / "confidence_log.jsonl"
            repair_record = {
                "ts": time.time(),
                "event": "repair",
                "pages_repaired": target_pages,
                "weak_threshold": body.weak_threshold,
                "source": "api",
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(repair_record) + "\n")

            return {
                "dry_run": False,
                "pages_targeted": target_pages,
                "repaired": len(target_pages),
                "failed": 0,
                "message": f"Repaired {len(target_pages)} pages. Run retrieval trials to measure improvement.",
            }
        except Exception as exc:  # noqa: BLE001 - REST boundary
            raise _as_http_error(exc) from exc

    # ── Static web UI (Node-free) ────────────────────────────────────────────
    # `provenant serve` copies the Next.js static export into _WEB_CACHE_DIR.
    # We mount /_next for hashed JS/CSS bundles, then a catch-all SPA handler
    # returns the pre-built HTML for every non-API route.  If the cache dir
    # doesn't exist yet the server starts fine — only /api/* routes are live.

    _next_dir = _WEB_CACHE_DIR / "_next"
    if _next_dir.exists():
        app.mount("/_next", StaticFiles(directory=str(_next_dir)), name="next-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        web = _WEB_CACHE_DIR
        if not web.exists():
            raise HTTPException(
                status_code=503,
                detail="Web UI not built yet. Run `provenant serve` to build it.",
            )
        # Next.js export writes /knowledge → knowledge.html (no trailing slash)
        for candidate in (
            web / f"{full_path}.html",        # /knowledge → knowledge.html
            web / full_path / "index.html",   # /knowledge/ → knowledge/index.html
            web / "index.html",               # SPA root fallback
        ):
            if candidate.is_file():
                return FileResponse(str(candidate))
        raise HTTPException(status_code=404, detail=f"Not found: {full_path}")

    return app
