"""SWE-bench Verified file-localization runner for Stratum.

This benchmark scores whether Stratum retrieves files changed by the gold patch.
It does not run tests or the SWE-bench Docker harness.

Smoke test:
    python scripts/swebench_localization.py --repo-filter pallets/flask --limit 1

Full run:
    python scripts/swebench_localization.py --output scripts/results
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
DEFAULT_REPO_DIR = Path("D:/GitHub/swebench_repos")
DEFAULT_OUTPUT = ROOT / "scripts" / "results"
YOTTA_BASE_URL = "https://gateway.yottalabs.ai/api/maas"
DB_FILENAMES = ("stratum.db", "wiki.db")

_CURRENT_ENGINE: Any | None = None
_CURRENT_REPO: Path | None = None
_CURRENT_USE_LANCE: bool = False

_STOPWORDS = {
    "Add",
    "Allow",
    "And",
    "AttributeError",
    "Cannot",
    "DeprecationWarning",
    "Error",
    "Exception",
    "False",
    "Fix",
    "For",
    "From",
    "ImportError",
    "IndexError",
    "KeyError",
    "Not",
    "None",
    "Regression",
    "Return",
    "RuntimeError",
    "The",
    "This",
    "True",
    "TypeError",
    "Use",
    "ValueError",
    "Warning",
    "When",
    "With",
}


class suppress:
    def __init__(self, *exceptions: type[BaseException]) -> None:
        self.exceptions = exceptions or (Exception,)

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return exc_type is not None and issubclass(exc_type, self.exceptions)


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True, check=False)
        else:
            proc.kill()
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(exc.cmd, exc.timeout, output=stdout, stderr=stderr) from exc
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _load_dataset() -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("Missing dependency: datasets. Run: pip install datasets pyarrow tqdm") from exc

    ds = load_dataset(DATASET_NAME, split="test")
    return [dict(row) for row in ds]


def parse_gold_files(patch: str) -> list[str]:
    files: list[str] = []
    for line in (patch or "").splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip().replace("\\", "/")
            if path and path != "/dev/null" and path not in files:
                files.append(path)
    return files


def _repo_path(repo_dir: Path, repo: str) -> Path:
    return repo_dir / repo.replace("/", "__")


def _clone_repo(repo: str, repo_dir: Path) -> Path:
    dest = _repo_path(repo_dir, repo)
    if (dest / ".git").is_dir():
        return dest
    if dest.exists() and any(dest.iterdir()):
        raise RuntimeError(f"destination exists and is not a git repo: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _run(["git", "clone", "--depth=1", f"https://github.com/{repo}.git", str(dest)], timeout=900)
    if result.returncode != 0:
        with suppress(Exception):
            if dest.exists():
                shutil.rmtree(dest)
        raise RuntimeError((result.stderr or result.stdout or "git clone failed").strip())
    return dest


def _index_db_path(repo_path: Path) -> Path | None:
    for name in DB_FILENAMES:
        db = repo_path / ".provenant" / name
        if db.exists() and db.stat().st_size > 0:
            return db
    return None


def _has_generated_pages(repo_path: Path) -> bool:
    return _index_stats(repo_path)["generated_pages"] > 0


def _sqlite_uri(db: Path) -> str:
    return f"file:{db.as_posix()}?mode=ro&immutable=1"


def _index_stats(repo_path: Path) -> dict[str, Any]:
    db = _index_db_path(repo_path)
    stats: dict[str, Any] = {
        "repo_path": str(repo_path),
        "db_path": str(db) if db else "",
        "db_exists": bool(db),
        "generated_pages": 0,
        "file_pages": 0,
        "wiki_symbols": 0,
        "latest_job": None,
        "valid": False,
        "reason": "missing db",
    }
    if db is None:
        return stats

    import sqlite3

    try:
        con = sqlite3.connect(_sqlite_uri(db), uri=True)
        try:
            row = con.execute("select count(*) from wiki_pages where length(coalesce(summary, content, '')) > 0").fetchone()
            stats["generated_pages"] = int(row[0] or 0)
            row = con.execute(
                "select count(*) from wiki_pages where page_type = 'file_page' and length(coalesce(summary, content, '')) > 0"
            ).fetchone()
            stats["file_pages"] = int(row[0] or 0)
        except sqlite3.OperationalError:
            row = con.execute("select count(*) from pages where length(coalesce(summary, content, '')) > 0").fetchone()
            stats["generated_pages"] = int(row[0] or 0)
            row = con.execute(
                "select count(*) from pages where page_type = 'file_page' and length(coalesce(summary, content, '')) > 0"
            ).fetchone()
            stats["file_pages"] = int(row[0] or 0)
        with suppress(Exception):
            row = con.execute("select count(*) from wiki_symbols").fetchone()
            stats["wiki_symbols"] = int(row[0] or 0)
        con.close()
    except Exception as exc:
        stats["reason"] = f"db read failed: {exc}"
        return stats

    jobs_dir = repo_path / ".provenant" / "jobs"
    latest_job = None
    if jobs_dir.is_dir():
        jobs = sorted(jobs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for job_path in jobs[:1]:
            with suppress(Exception):
                job = json.loads(job_path.read_text(encoding="utf-8"))
                latest_job = {
                    "path": str(job_path),
                    "status": job.get("status"),
                    "total_pages": int(job.get("total_pages") or 0),
                    "completed_pages": int(job.get("completed_pages") or 0),
                    "failed_pages": int(job.get("failed_pages") or 0),
                    "updated_at": job.get("updated_at"),
                }
    stats["latest_job"] = latest_job

    if stats["generated_pages"] <= 0:
        stats["reason"] = "zero generated pages"
        return stats

    if latest_job and latest_job["total_pages"] > 0:
        ratio = latest_job["completed_pages"] / latest_job["total_pages"]
        stats["job_completion"] = ratio
        if ratio < 0.8:
            stats["reason"] = f"job completion {ratio:.1%} below threshold"
            return stats

    if stats["file_pages"] <= 0:
        stats["reason"] = "zero generated file pages"
        return stats

    stats["valid"] = True
    stats["reason"] = "ok"
    return stats


def _index_is_valid(repo_path: Path, threshold: float = 0.8) -> tuple[bool, dict[str, Any]]:
    stats = _index_stats(repo_path)
    latest_job = stats.get("latest_job")
    if stats.get("generated_pages", 0) <= 0 or stats.get("file_pages", 0) <= 0:
        return False, stats
    if latest_job and latest_job.get("total_pages", 0) > 0:
        ratio = latest_job.get("completed_pages", 0) / latest_job.get("total_pages", 1)
        stats["job_completion"] = ratio
        if ratio < threshold:
            stats["valid"] = False
            stats["reason"] = f"job completion {ratio:.1%} below threshold"
            return False, stats
    stats["valid"] = True
    stats["reason"] = "ok"
    return True, stats


def _init_stratum(repo_path: Path, args: argparse.Namespace) -> tuple[bool, str, bool]:
    if args.skip_init and _index_db_path(repo_path) is not None:
        return True, "existing index", False
    valid, stats = _index_is_valid(repo_path, threshold=args.validation_threshold)
    if not args.force_init and valid:
        return True, f"existing valid generated wiki ({stats['generated_pages']} pages)", False

    env = os.environ.copy()
    env["OPENAI_BASE_URL"] = args.base_url
    env.setdefault("PROVENANT_EMBEDDER", args.embedder)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    cmd = [
        sys.executable,
        "-B",
        "-m",
        "stratum.cli.main",
        "init",
        "--provider",
        "openai",
        "--model",
        args.model,
        "--embedder",
        args.embedder,
        "--reasoning",
        args.reasoning,
        "--concurrency",
        str(args.concurrency),
        "--no-claude-md",
        "-y",
    ]
    if args.smoke:
        args.init_test_run = True

    if args.init_test_run:
        cmd.append("--test-run")
    if args.force_init:
        cmd.append("--force")
    if args.smoke:
        cmd.extend(["--skip-tests", "--skip-infra", "-x", "docs/", "-x", "examples/"])
    cmd.append(str(repo_path))

    try:
        result = _run(cmd, cwd=ROOT, env=env, timeout=args.init_timeout)
    except subprocess.TimeoutExpired:
        return False, f"stratum init timed out after {args.init_timeout} seconds", False

    if result.returncode != 0:
        if _has_generated_pages(repo_path):
            return True, "generated wiki exists despite nonzero init exit", True
        msg = "\n".join(x for x in (result.stdout, result.stderr) if x).strip()
        return False, msg[-4000:] or "stratum init failed", False
    if not _has_generated_pages(repo_path):
        return False, "stratum init completed but generated pages were not found", False
    return True, "indexed", True


async def _init_state(repo_path: Path, use_lance: bool = False) -> None:
    global _CURRENT_ENGINE, _CURRENT_REPO, _CURRENT_USE_LANCE

    repo_path = repo_path.resolve()
    if _CURRENT_REPO == repo_path and _CURRENT_USE_LANCE == use_lance:
        return

    if _CURRENT_ENGINE is not None:
        with suppress(Exception):
            await _CURRENT_ENGINE.dispose()

    from provenant.core.persistence.database import create_engine, create_session_factory
    from provenant.core.persistence.search import FullTextSearch
    from provenant.core.persistence.vector_store import InMemoryVectorStore
    from provenant.core.workspace.registry import RepoContext
    from provenant.llm.providers.embedding.base import MockEmbedder
    from provenant.server.mcp_server import _state

    if not hasattr(RepoContext, "repo_path"):
        RepoContext.repo_path = property(lambda self: str(self.path))  # type: ignore[attr-defined]

    db_path = _index_db_path(repo_path)
    if db_path is None:
        raise FileNotFoundError(f"No Stratum index found in {repo_path / '.provenant'}")

    engine = create_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_factory = create_session_factory(engine)
    fts = FullTextSearch(engine)
    await fts.ensure_index()

    mock_embedder = MockEmbedder()
    ready = asyncio.Event()
    ready.set()

    _state._repo_path = str(repo_path)
    _state._session_factory = session_factory
    _state._fts = fts
    _state._registry = None
    _state._workspace_root = None
    _state._cross_repo_enricher = None
    _state._vector_store = InMemoryVectorStore(embedder=mock_embedder)
    _state._decision_store = InMemoryVectorStore(embedder=mock_embedder)
    _state._vector_store_ready = ready

    if use_lance:
        lance_dir = repo_path / ".provenant" / "lancedb"
        if lance_dir.exists():
            try:
                from provenant.core.persistence.vector_store import LanceDBVectorStore
                # Use the same embedder that was used to build the index.
                # If OPENAI_EMBEDDING_* vars are set (Fireworks), use OpenAI embedder.
                # Otherwise fall back to local 384-dim embedder.
                _embed_key = os.environ.get("OPENAI_EMBEDDING_API_KEY") or os.environ.get("OPENAI_API_KEY")
                if _embed_key:
                    from provenant.llm.providers.embedding.openai import OpenAIEmbedder
                    embedder = OpenAIEmbedder()
                    _embed_label = f"OpenAI ({os.environ.get('OPENAI_EMBEDDING_MODEL', 'default')})"
                else:
                    from provenant.llm.providers.embedding.local import LocalEmbedder
                    embedder = LocalEmbedder()
                    _embed_label = "local"
                vs = LanceDBVectorStore(str(lance_dir), embedder=embedder)
                await vs._ensure_connected()
                _state._vector_store = vs
                print(f"  vector_store: LanceDB loaded ({lance_dir}) [{_embed_label}]")
            except Exception as exc:
                print(f"  vector_store: LanceDB failed ({exc}) — HyDE disabled for this repo")
        else:
            print(f"  vector_store: no LanceDB dir at {lance_dir} — HyDE disabled for this repo")

    _CURRENT_ENGINE = engine
    _CURRENT_REPO = repo_path
    _CURRENT_USE_LANCE = use_lance


def _as_path(value: Any, repo_path: Path) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("path", "file", "file_path", "target_path", "source_path"):
            if key in value:
                return _as_path(value[key], repo_path)
        return None

    path = str(value).strip().strip("\"'").replace("\\", "/")
    if not path:
        return None
    path = path.split("#", 1)[0]
    if "::" in path:
        path = path.split("::", 1)[0]

    repo_norm = str(repo_path.resolve()).replace("\\", "/").rstrip("/") + "/"
    if path.lower().startswith(repo_norm.lower()):
        path = path[len(repo_norm):]
    elif len(path) >= 3 and path[1:3] == ":/":
        with suppress(Exception):
            path = str(Path(path).resolve().relative_to(repo_path.resolve())).replace("\\", "/")
    return path.lstrip("./").lstrip("/") or None


def _is_test_path(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    parts = p.split("/")
    return "test" in parts or "tests" in parts or "/test_" in p or p.startswith("test_") or p.endswith(("_test.py", ".test.ts", ".spec.ts", ".test.js", ".spec.js"))


def _unique(paths: list[Any], repo_path: Path, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    non_tests: list[str] = []
    tests: list[str] = []
    for raw in paths:
        path = _as_path(raw, repo_path)
        if not path or path in seen:
            continue
        seen.add(path)
        (tests if _is_test_path(path) else non_tests).append(path)
    out = non_tests + tests
    return out[:limit] if limit is not None else out


async def _search_paths(issue_text: str, repo_path: Path, limit: int) -> list[str]:
    from sqlalchemy import select

    from provenant.core.persistence.database import get_session
    from provenant.core.persistence.models import Page
    from provenant.server.mcp_server import _state
    from provenant.server.mcp_server.tool_search import stratum_search

    payload = await stratum_search(query=issue_text[:1200], limit=limit)
    results = payload.get("results", []) if isinstance(payload, dict) else []
    direct = [
        item.get("target_path") or item.get("path") or item.get("file_path")
        for item in results
        if isinstance(item, dict)
    ]
    paths = _unique(direct, repo_path)

    missing_ids = [
        item.get("page_id")
        for item in results
        if isinstance(item, dict)
        and not (item.get("target_path") or item.get("path") or item.get("file_path"))
        and item.get("page_id")
    ]
    if missing_ids:
        async with get_session(_state._session_factory) as session:
            res = await session.execute(select(Page.id, Page.target_path).where(Page.id.in_(missing_ids)))
            by_id = {row[0]: row[1] for row in res.all()}
        paths = _unique(paths + [by_id.get(pid) for pid in missing_ids], repo_path)
    return paths


def _extract_identifiers(issue_text: str, limit: int = 8) -> list[str]:
    raw = re.findall(r"`([^`]+)`|\b([A-Z][A-Za-z0-9_]{2,})\b|\b([a-z_][a-z0-9_]{3,})\b", issue_text)
    out: list[str] = []
    for parts in raw:
        token = next((p for p in parts if p), "").strip()
        token = token.split("(", 1)[0].split(".", 1)[0].split("::", 1)[0]
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", token):
            continue
        variants = [token]
        if token.endswith("ies") and len(token) > 4:
            variants.append(token[:-3] + "y")
        if token.endswith("s") and not token.endswith("ss") and len(token) > 4:
            variants.append(token[:-1])
        for variant in variants:
            if variant in _STOPWORDS or len(variant) < 3:
                continue
            if variant not in out:
                out.append(variant)
                if len(out) >= limit:
                    return out
    return out


async def _symbol_paths(issue_text: str, repo_path: Path) -> list[str]:
    from sqlalchemy import or_, select

    from provenant.core.persistence.database import get_session
    from provenant.core.persistence.models import WikiSymbol
    from provenant.server.mcp_server import _state
    from provenant.server.mcp_server.tool_symbol import stratum_symbol

    paths: list[str] = []
    async with get_session(_state._session_factory) as session:
        for name in _extract_identifiers(issue_text, limit=8):
            res = await session.execute(select(WikiSymbol).where(or_(WikiSymbol.name == name, WikiSymbol.qualified_name == name)))
            rows = list(res.scalars().all())
            if not rows:
                continue

            def rank(row: Any) -> tuple[int, int, str]:
                fp = (row.file_path or "").replace("\\", "/")
                return (0 if name.lower() in Path(fp).stem.lower() else 1, 1 if _is_test_path(fp) else 0, fp)

            for row in sorted(rows, key=rank)[:2]:
                payload = await stratum_symbol(row.symbol_id)
                path = _as_path(payload, repo_path)
                if path:
                    paths.append(path)
    return _unique(paths, repo_path)


async def query_stratum(issue_text: str, repo_path: Path, k: int) -> list[str]:
    await _init_state(repo_path)
    symbol_files = await _symbol_paths(issue_text, repo_path)
    search_files = await _search_paths(issue_text, repo_path, limit=k)
    return _unique(symbol_files + search_files, repo_path, limit=k)


async def query_stratum_hyde(issue_text: str, repo_path: Path, k: int) -> tuple[list[str], bool]:
    """BM25 + HyDE vector retrieval via get_answer(). Returns (paths, hyde_fired)."""
    await _init_state(repo_path, use_lance=True)

    from provenant.server.mcp_server.tool_answer import stratum_ask

    result = await stratum_ask(
        question=issue_text,
        force_synthesize=False,
        hyde=True,
    )

    hyde_used: bool = bool(result.get("_meta", {}).get("hyde_used", False))

    # stratum_ask caps internal retrieval at 5 hits; also call _search_paths at
    # full depth so HyDE and BM25 evals both get k candidates from FTS.
    fallback = [str(p) for p in result.get("fallback_targets", []) if p]
    retrieval_paths = [h.get("target_path", "") for h in result.get("retrieval", []) if h.get("target_path")]
    bm25_files = await _search_paths(issue_text, repo_path, limit=k)
    symbol_files = await _symbol_paths(issue_text, repo_path)
    combined = _unique(symbol_files + fallback + retrieval_paths + bm25_files, repo_path, limit=k)
    return combined, hyde_used


def _normalize_path(p: str) -> str:
    """Strip src/ prefix and normalize separators for path matching."""
    p = p.replace("\\", "/")
    # Strip src/ layout prefix (e.g. requests, attrs use src/ layout)
    if p.startswith("src/"):
        p = p[4:]
    return p


def score_task(predicted: list[str], gold: list[str]) -> dict[str, float | int]:
    gold_set = set(gold)
    gold_norm = set(_normalize_path(g) for g in gold)
    pred_norm = [_normalize_path(p) for p in predicted]

    def _hits(top_raw: list[str]) -> int:
        top = set(top_raw)
        top_n = set(_normalize_path(p) for p in top_raw)
        return int(bool((top & gold_set) or (top_n & gold_norm)))

    def _mrr(pred: list[str]) -> float:
        for rank, p in enumerate(pred, start=1):
            if p in gold_set or _normalize_path(p) in gold_norm:
                return 1.0 / rank
        return 0.0

    scores: dict[str, float | int] = {}
    for k in (5, 10):
        top = predicted[:k]
        scores[f"coverage@{k}"] = _hits(top)
        hits = len(set(top) & gold_set) or len(set(_normalize_path(p) for p in top) & gold_norm)
        scores[f"precision@{k}"] = hits / k
    scores["mrr"] = _mrr(predicted)
    scores["exact@5"] = int(set(predicted[:5]) == gold_set)
    return scores


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows if key in row]
    return statistics.fmean(values) if values else 0.0


def _filtered_tasks(args: argparse.Namespace) -> list[dict[str, Any]]:
    tasks = _load_dataset()
    if args.repo_filter:
        wanted = {x.strip() for x in args.repo_filter.split(",") if x.strip()}
        tasks = [task for task in tasks if task.get("repo") in wanted]
    if args.limit:
        tasks = tasks[: args.limit]
    return tasks


def _group_tasks(tasks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped[str(task["repo"])].append(task)
    return grouped


def _print_repo_counts(tasks: list[dict[str, Any]]) -> None:
    counts = Counter(str(task["repo"]) for task in tasks)
    gold_counts: Counter[str] = Counter()
    for task in tasks:
        gold_counts[str(task["repo"])] += len(parse_gold_files(str(task.get("patch") or "")))

    print(f"{'Repo':<38} {'Tasks':>6} {'GoldFiles':>9}")
    print("-" * 56)
    for repo, count in counts.most_common():
        print(f"{repo:<38} {count:>6} {gold_counts[repo]:>9}")
    print("-" * 56)
    print(f"{'TOTAL':<38} {sum(counts.values()):>6} {sum(gold_counts.values()):>9}")


def _write_validation_report(output_dir: Path, report: list[dict[str, Any]], smoke: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ("swebench_localization_smoke_index_validation.json" if smoke else "swebench_localization_index_validation.json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nIndex validation written to: {path}")


def _validate_indexes(grouped: dict[str, list[dict[str, Any]]], repo_dir: Path, output_dir: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    print(f"{'Repo':<38} {'Tasks':>6} {'Valid':>6} {'Pages':>7} {'FilePg':>7} {'Job':>9}  Reason")
    print("-" * 94)
    for repo, repo_tasks in grouped.items():
        repo_path = _repo_path(repo_dir, repo)
        valid, stats = _index_is_valid(repo_path, threshold=args.validation_threshold)
        latest_job = stats.get("latest_job") or {}
        job_text = ""
        if latest_job:
            total = latest_job.get("total_pages") or 0
            done = latest_job.get("completed_pages") or 0
            job_text = f"{done}/{total}" if total else str(done)
        row = {
            "repo": repo,
            "tasks": len(repo_tasks),
            **stats,
            "valid": valid,
        }
        rows.append(row)
        print(
            f"{repo:<38} {len(repo_tasks):>6} {str(valid):>6} "
            f"{int(stats.get('generated_pages') or 0):>7} {int(stats.get('file_pages') or 0):>7} "
            f"{job_text:>9}  {stats.get('reason')}"
        )
    _write_validation_report(output_dir, rows, smoke=args.smoke)
    return rows


async def async_main(args: argparse.Namespace) -> int:
    tasks = _filtered_tasks(args)
    if args.print_repo_counts:
        _print_repo_counts(tasks)
        return 0
    if not tasks:
        raise SystemExit("No tasks selected.")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = Path(args.repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)

    grouped = _group_tasks(tasks)
    if args.validate_indexes:
        _validate_indexes(grouped, repo_dir, output_dir, args)
        return 0

    rows: list[dict[str, Any]] = []
    repo_status: dict[str, Any] = {}
    repos_indexed = 0

    print(f"Tasks selected: {len(tasks)}")
    print(f"Repos selected: {len(grouped)}")
    print(f"Output: {output_dir}")

    for repo, repo_tasks in grouped.items():
        print(f"\n--- {repo} ({len(repo_tasks)} tasks) ---")
        try:
            repo_path = _clone_repo(repo, repo_dir)
        except Exception as exc:
            repo_status[repo] = {"status": "clone_failed", "message": str(exc)}
            for task in repo_tasks:
                rows.append({"instance_id": task["instance_id"], "repo": repo, "error": f"clone_failed: {exc}"})
            continue

        if args.eval_only:
            ok, stats = _index_is_valid(repo_path, threshold=args.validation_threshold)
            msg = stats.get("reason", "")
            did_index = False
        else:
            ok, msg, did_index = _init_stratum(repo_path, args)
            if did_index:
                repos_indexed += 1

        repo_status[repo] = {"status": "ok" if ok else "index_failed", "message": msg, "repo_path": str(repo_path), "indexed_now": did_index}
        print(f"  index: {'OK' if ok else 'FAILED'} ({msg})")
        if not ok:
            if not args.init_only:
                for task in repo_tasks:
                    rows.append({"instance_id": task["instance_id"], "repo": repo, "error": f"index_failed: {msg}"})
            continue

        if args.init_only:
            continue

        for task in repo_tasks:
            gold_files = parse_gold_files(str(task.get("patch") or ""))
            if not gold_files:
                rows.append({"instance_id": task["instance_id"], "repo": repo, "error": "no_gold_files"})
                continue
            try:
                if args.hyde:
                    predicted, hyde_fired = await query_stratum_hyde(str(task.get("problem_statement") or ""), repo_path, k=10)
                else:
                    predicted = await query_stratum(str(task.get("problem_statement") or ""), repo_path, k=10)
                    hyde_fired = False
                scores = score_task(predicted, gold_files)
                row = {
                    "instance_id": task["instance_id"],
                    "repo": repo,
                    "gold_files": gold_files,
                    "predicted_top10": predicted,
                    "hyde_fired": hyde_fired,
                    **scores,
                }
                rows.append(row)
                print(f"  {task['instance_id']}: cov@5={scores['coverage@5']} cov@10={scores['coverage@10']} mrr={float(scores['mrr']):.3f}")
            except Exception as exc:
                rows.append({"instance_id": task["instance_id"], "repo": repo, "gold_files": gold_files, "error": f"query_failed: {exc}"})

    _tag = "smoke" if args.smoke else ("hyde" if args.hyde else "")
    _prefix = f"swebench_localization_{_tag}_" if _tag else "swebench_localization_"
    raw_path = output_dir / f"{_prefix}raw.jsonl"
    summary_path = output_dir / f"{_prefix}summary.json"
    status_path = output_dir / f"{_prefix}status.json"

    with raw_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    scored = [row for row in rows if "error" not in row]
    summary = {
        "total_tasks": len(rows),
        "scored_tasks": len(scored),
        "errored_tasks": len(rows) - len(scored),
        "repos": len(grouped),
        "repos_indexed": repos_indexed,
        "coverage@5": _mean(scored, "coverage@5"),
        "coverage@10": _mean(scored, "coverage@10"),
        "precision@5": _mean(scored, "precision@5"),
        "precision@10": _mean(scored, "precision@10"),
        "mrr": _mean(scored, "mrr"),
        "exact@5": _mean(scored, "exact@5"),
        "hyde": args.hyde,
        "hyde_fired_count": sum(1 for r in scored if r.get("hyde_fired")),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    status_path.write_text(json.dumps({"repo_status": repo_status, **summary}, indent=2), encoding="utf-8")

    print("\n=== RESULTS ===")
    print(f"Tasks scored: {summary['scored_tasks']}/{summary['total_tasks']}")
    print(f"Coverage@5:  {summary['coverage@5']:.1%}")
    print(f"Coverage@10: {summary['coverage@10']:.1%}")
    print(f"Precision@5: {summary['precision@5']:.3f}")
    print(f"MRR:         {summary['mrr']:.3f}")
    print(f"Raw:         {raw_path}")
    print(f"Summary:     {summary_path}")
    print(f"Status:      {status_path}")

    if _CURRENT_ENGINE is not None:
        with suppress(Exception):
            await _CURRENT_ENGINE.dispose()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--repo-dir", default=str(DEFAULT_REPO_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repo-filter", default="")
    parser.add_argument("--model", default="deepseek-v3.2")
    parser.add_argument("--base-url", default=YOTTA_BASE_URL)
    parser.add_argument("--embedder", default="local", choices=["local", "openai", "gemini", "none", "mock"])
    parser.add_argument("--reasoning", default="auto", choices=["auto", "off", "minimal"])
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--init-timeout", type=int, default=3600)
    parser.add_argument("--skip-init", action="store_true")
    parser.add_argument("--force-init", action="store_true")
    parser.add_argument("--init-test-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--init-only", action="store_true")
    parser.add_argument("--eval-only", action="store_true")
    parser.add_argument("--validate-indexes", action="store_true")
    parser.add_argument("--print-repo-counts", action="store_true")
    parser.add_argument("--validation-threshold", type=float, default=0.8)
    parser.add_argument("--hyde", action="store_true", help="Use HyDE + LanceDB vector retrieval instead of BM25-only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
