"""
Stratum benchmark runner.

Runs each question from a JSONL file in four modes:
  - stratum:   compress=True,  hyde=True  (full Stratum — HyDE + compression)
  - no_hyde:   compress=True,  hyde=False (compression only, HyDE ablation)
  - baseline:  compress=False, hyde=False (all wiki pages, no pruning — Repowise equivalent)
  - naive:     raw source files via BM25, no wiki, no compression (naive file reading)

The naive mode is the apples-to-apples comparison against Repowise's published claims.
Token counts for naive show what an agent would consume reading raw files directly.

Usage:
    python scripts/benchmark.py \
        --repo ./flask \
        --questions scripts/questions/flask.jsonl \
        --output scripts/results/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# File extensions to include in naive BM25 retrieval
# ---------------------------------------------------------------------------
_NAIVE_EXTENSIONS = {".py", ".ts", ".js", ".go", ".rs", ".java", ".c", ".cpp", ".h"}
_NAIVE_SKIP_DIRS  = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".provenant"}
_NAIVE_TOP_K      = 15  # typical naive agent reads top BM25 files uncapped


def _naive_bm25_search(repo_path: Path, question: str, top_k: int = _NAIVE_TOP_K) -> list[dict]:
    """BM25 search over raw source files. Returns top_k as {path, content, tokens_approx}."""
    try:
        from rank_bm25 import BM25Okapi  # type: ignore
    except ImportError:
        # Fallback: just return all files up to top_k sorted by size
        files = []
        for f in repo_path.rglob("*"):
            if f.suffix in _NAIVE_EXTENSIONS and not any(d in f.parts for d in _NAIVE_SKIP_DIRS):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    files.append({"path": str(f.relative_to(repo_path)), "content": content})
                except Exception:
                    pass
        return files[:top_k]

    files = []
    for f in repo_path.rglob("*"):
        if f.is_file() and f.suffix in _NAIVE_EXTENSIONS:
            if any(d in f.parts for d in _NAIVE_SKIP_DIRS):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                files.append({"path": str(f.relative_to(repo_path)), "content": content})
            except Exception:
                pass

    if not files:
        return []

    tokenized = [re.split(r"\W+", doc["content"].lower()) for doc in files]
    bm25 = BM25Okapi(tokenized)
    query_tokens = re.split(r"\W+", question.lower())
    scores = bm25.get_scores(query_tokens)

    ranked = sorted(zip(scores, files), key=lambda x: x[0], reverse=True)
    return [f for _, f in ranked[:top_k]]


async def _run_naive(question: str, repo_path: Path, provider_name: str = "openai") -> dict:
    """Answer a question using raw BM25 file retrieval — no wiki, no compression."""
    import openai as _openai

    t0 = time.monotonic()
    try:
        files = await asyncio.to_thread(_naive_bm25_search, repo_path, question)
        if not files:
            raise RuntimeError("No source files found in repo")

        context_parts = []
        for f in files:
            content = f["content"]  # no cap — true naive agent reads full files
            context_parts.append(f"### {f['path']}\n```\n{content}\n```")
        context_block = "\n\n".join(context_parts)

        prompt = (
            f"You are an expert software engineer. Answer the following question about the codebase "
            f"using only the source files provided.\n\n"
            f"Question: {question}\n\n"
            f"Source files:\n{context_block}\n\n"
            f"Answer:"
        )

        api_key  = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL") or None
        model    = os.environ.get("BENCHMARK_NAIVE_MODEL", "deepseek-v3.2")
        client = _openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )

        answer = response.choices[0].message.content or ""
        tokens_in  = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
        # DeepSeek-V3.2 via Yotta Labs pricing (approx)
        cost_usd = (tokens_in * 0.27 + tokens_out * 1.10) / 1_000_000

        return {
            "answer": answer,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "files_read": len(files),
            "file_paths": [f["path"] for f in files],
            "latency_ms": round((time.monotonic() - t0) * 1000),
            "error": None,
        }
    except Exception as exc:
        return {
            "answer": "",
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "files_read": 0,
            "file_paths": [],
            "latency_ms": round((time.monotonic() - t0) * 1000),
            "error": str(exc),
        }


async def _init_stratum_state(repo_path: Path) -> None:
    """Initialize the MCP server's global _state so get_answer() works without a live server."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from provenant.core.persistence.database import init_db, resolve_db_url
    from provenant.core.persistence.search import FullTextSearch
    from provenant.core.persistence.vector_store import InMemoryVectorStore
    from provenant.core.workspace.registry import RepoContext
    from provenant.llm.providers.embedding.base import MockEmbedder
    from provenant.server.mcp_server import _state

    # RepoContext.repo_path is accessed in tool_answer.py but the dataclass only
    # has .path — patch it in once so stratum_ask() doesn't crash.
    if not hasattr(RepoContext, "repo_path"):
        RepoContext.repo_path = property(lambda self: str(self.path))  # type: ignore[attr-defined]

    _state._repo_path = str(repo_path)
    db_url = resolve_db_url(str(repo_path))
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_async_engine(db_url, connect_args=connect_args)
    await init_db(engine)
    _state._session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    _state._fts = FullTextSearch(engine)
    await _state._fts.ensure_index()

    _state._vector_store_ready = asyncio.Event()
    _state._vector_store = InMemoryVectorStore(embedder=MockEmbedder())  # fallback

    try:
        from provenant.server.mcp_server._server import _resolve_embedder
        embedder = _resolve_embedder()
        lance_dir = repo_path / ".provenant" / "lancedb"
        if lance_dir.exists():
            from provenant.core.persistence.vector_store import LanceDBVectorStore
            vs = LanceDBVectorStore(str(lance_dir), embedder=embedder)
            await vs._ensure_connected()
            _state._vector_store = vs
            print("  Vector store: LanceDB loaded — HyDE will use real embeddings")
        else:
            print("  Vector store: no LanceDB dir found — HyDE will use MockEmbedder (random vectors)")
    except Exception as e:
        print(f"  Vector store: fallback to Mock ({type(e).__name__}: {e})")

    _state._vector_store_ready.set()

    try:
        n_vecs = len(await _state._vector_store.list_page_ids())
        if n_vecs == 0:
            print(
                "  [warn] Vector store is empty — HyDE will always fall back to BM25. "
                "Re-index with an embedder to enable semantic retrieval."
            )
        else:
            print(f"  Vector store: {n_vecs} page embeddings available for HyDE")
    except Exception:
        pass


async def _run_one(question: str, repo_path: Path, compress: bool, hyde: bool = True) -> dict:
    """Call get_answer() directly (no MCP socket) and return structured result."""
    from provenant.server.mcp_server.tool_answer import stratum_ask

    t0 = time.monotonic()
    try:
        result = await stratum_ask(
            question=question,
            compress=compress,
            force_synthesize=True,
            hyde=hyde,
        )
    except Exception as exc:
        return {
            "error": str(exc),
            "answer": "",
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "compression_pct": 0.0,
            "files_pruned": 0,
            "initial_files": 0,
            "final_files": 0,
            "hyde_used": False,
            "latency_ms": round((time.monotonic() - t0) * 1000),
            "compress": compress,
            "hyde": hyde,
        }
    elapsed_ms = round((time.monotonic() - t0) * 1000)

    compression = result.get("compression", {})
    meta = result.get("_meta", {})

    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "confidence": result.get("confidence", ""),
        "tokens_in": meta.get("tokens_in", 0),
        "tokens_out": meta.get("tokens_out", 0),
        "cost_usd": meta.get("cost_usd", 0.0),
        "compression_pct": compression.get("compression_pct", 0.0),
        "files_pruned": compression.get("files_pruned", 0),
        "initial_files": compression.get("initial_files", 0),
        "final_files": compression.get("final_files", 0),
        "pruned_files": compression.get("pruned_files", []),
        "hyde_used": meta.get("hyde_used", False),
        "latency_ms": elapsed_ms,
        "compress": compress,
        "hyde": hyde,
        "error": None,
    }


async def run_benchmark(
    questions_path: Path,
    repo_path: Path,
    output_dir: Path,
) -> None:
    questions = []
    with open(questions_path) as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "raw.jsonl"

    print(f"Initializing stratum state for {repo_path}...")
    await _init_stratum_state(repo_path)
    print("State initialized.\n")

    total = len(questions)
    print(f"Running {total} questions × 4 modes = {total * 4} LLM calls")
    print(f"  Mode 1 — stratum:  compress=True,  hyde=True  (HyDE + compression)")
    print(f"  Mode 2 — no_hyde:  compress=True,  hyde=False (compression only)")
    print(f"  Mode 3 — baseline: compress=False, hyde=False (all wiki pages — Repowise equivalent)")
    print(f"  Mode 4 — naive:    raw BM25 file reading, no wiki (naive agent baseline)")
    print(f"Repo: {repo_path}")
    print(f"Output: {raw_path}\n")

    with open(raw_path, "w") as out:
        for i, q in enumerate(questions, 1):
            qid = q["id"]
            question = q["question"]
            print(f"[{i}/{total}] {qid}: {question[:60]}...")

            r_stratum  = await _run_one(question, repo_path, compress=True,  hyde=True)
            r_no_hyde  = await _run_one(question, repo_path, compress=True,  hyde=False)
            r_baseline = await _run_one(question, repo_path, compress=False, hyde=False)
            r_naive    = await _run_naive(question, repo_path)

            row = {
                "id": qid,
                "question": question,
                "tags": q.get("tags", []),
                "provenant":  r_stratum,
                "no_hyde":  r_no_hyde,
                "baseline": r_baseline,
                "naive":    r_naive,
            }
            out.write(json.dumps(row) + "\n")
            out.flush()

            tok_s  = r_stratum.get("tokens_in", 0)
            tok_nh = r_no_hyde.get("tokens_in", 0)
            tok_b  = r_baseline.get("tokens_in", 0)
            tok_n  = r_naive.get("tokens_in", 0)
            hyde_fired = r_stratum.get("hyde_used", False)
            print(
                f"  Stratum: {tok_s} tok | No-HyDE: {tok_nh} tok | "
                f"Wiki: {tok_b} tok | Naive: {tok_n} tok | "
                f"HyDE: {'yes' if hyde_fired else 'no'} | "
                f"Compression: {r_stratum.get('compression_pct', 0):.1f}%"
            )

    # --- Aggregate summary ---
    rows = []
    with open(raw_path) as f:
        for line in f:
            rows.append(json.loads(line))

    def _avg(vals: list[float]) -> float:
        return sum(vals) / max(len(vals), 1)

    s_tokens  = [r["provenant"].get("tokens_in", 0)  for r in rows if not r["provenant"].get("error")]
    nh_tokens = [r["no_hyde"].get("tokens_in", 0)  for r in rows if not r["no_hyde"].get("error")]
    b_tokens  = [r["baseline"].get("tokens_in", 0) for r in rows if not r["baseline"].get("error")]
    n_tokens  = [r["naive"].get("tokens_in", 0)    for r in rows if not r["naive"].get("error")]

    s_cost  = [r["provenant"].get("cost_usd", 0)  for r in rows]
    n_cost  = [r["naive"].get("cost_usd", 0)    for r in rows]

    s_files = [r["provenant"].get("final_files", 0)     for r in rows]
    n_files = [r["naive"].get("files_read", 0)         for r in rows]

    compressions = [r["provenant"].get("compression_pct", 0) for r in rows]
    files_pruned = [r["provenant"].get("files_pruned", 0)    for r in rows]
    hyde_fired   = sum(1 for r in rows if r["provenant"].get("hyde_used", False))

    total_n = len(rows)
    avg_s  = _avg(s_tokens)
    avg_nh = _avg(nh_tokens)
    avg_b  = _avg(b_tokens)
    avg_n  = _avg(n_tokens)

    token_reduction_vs_naive    = (1 - avg_s / max(avg_n, 1)) * 100
    token_reduction_vs_baseline = (1 - avg_s / max(avg_b, 1)) * 100
    hyde_delta                  = (1 - avg_s / max(avg_nh, 1)) * 100
    files_reduction_vs_naive    = (1 - _avg(s_files) / max(_avg(n_files), 1)) * 100
    cost_reduction_vs_naive     = (1 - _avg(s_cost) / max(_avg(n_cost), 1)) * 100
    naive_multiplier            = avg_n / max(avg_s, 1)

    print(f"\n{'='*70}")
    print(f"BENCHMARK SUMMARY ({total_n} questions)")
    print(f"{'='*70}")
    print(f"\n--- Token counts ---")
    print(f"Avg input tokens — Full Stratum (HyDE+compress):  {avg_s:.0f}")
    print(f"Avg input tokens — No HyDE (compress only):       {avg_nh:.0f}")
    print(f"Avg input tokens — Wiki baseline (no compress):   {avg_b:.0f}")
    print(f"Avg input tokens — Naive file reading:            {avg_n:.0f}")
    print(f"\n--- vs Naive file reading (Repowise-style metrics) ---")
    print(f"Token reduction vs naive:          {token_reduction_vs_naive:.1f}%  ({naive_multiplier:.1f}x fewer tokens)")
    print(f"Cost reduction vs naive:           {cost_reduction_vs_naive:.1f}%")
    print(f"Files read reduction vs naive:     {files_reduction_vs_naive:.1f}%")
    print(f"Avg files read — Stratum:          {_avg(s_files):.1f}")
    print(f"Avg files read — Naive:            {_avg(n_files):.1f}")
    print(f"\n--- Stratum internals ---")
    print(f"Token reduction vs wiki baseline:  {token_reduction_vs_baseline:.1f}%")
    print(f"HyDE token delta (vs no_hyde):     {hyde_delta:+.1f}%")
    print(f"Avg compression:                   {_avg(compressions):.1f}%")
    print(f"Avg pages pruned/query:            {_avg(files_pruned):.1f}")
    print(f"HyDE fired on:                     {hyde_fired}/{total_n} questions")
    print(f"\nRaw results: {raw_path}")
    print(f"Run judge.py next to score answer quality.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stratum benchmark runner (HyDE + compression vs naive)")
    parser.add_argument("--repo", required=True, help="Path to indexed repo (must have .stratum/)")
    parser.add_argument("--questions", required=True, help="Path to questions JSONL file")
    parser.add_argument("--output", default="scripts/results/", help="Output directory")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not (repo_path / ".provenant").exists():
        print(f"ERROR: {repo_path}/.stratum not found. Run 'stratum init {repo_path}' first.")
        sys.exit(1)

    asyncio.run(run_benchmark(
        questions_path=Path(args.questions),
        repo_path=repo_path,
        output_dir=Path(args.output),
    ))


if __name__ == "__main__":
    main()
