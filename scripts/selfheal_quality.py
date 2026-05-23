"""
Self-healing quality experiment.
Compares LLM judge scores on 4 low-confidence Django questions
BEFORE repair (stored answers from confidence_raw.jsonl)
vs AFTER repair (re-run now with repaired wiki).
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv("D:/GitHub/stratumv2/.env")
OPENAI_API_KEY   = os.environ.get("OPENAI_DIRECT_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
DJANGO_REPO      = Path("D:/GitHub/swebench_repos/django__django")

# Point at the existing .stratum/wiki.db (indexed before the provenant rename).
# resolve_db_url now looks for .provenant/wiki.db, which doesn't exist yet.
os.environ["PROVENANT_DB_URL"] = f"sqlite+aiosqlite:///{DJANGO_REPO.as_posix()}/.stratum/wiki.db"

# Use real OpenAI for synthesis (config.yaml says deepseek-v3.2 which is invalid on OpenAI)
os.environ.pop("OPENAI_BASE_URL", None)
os.environ["PROVENANT_MODEL"] = "gpt-4o"
os.environ["PROVENANT_PROVIDER"] = "openai"
CONFIDENCE_RAW   = Path("D:/GitHub/stratumv2/scripts/results/confidence_eval/confidence_raw.jsonl")
AFTER_REPAIR     = Path("D:/GitHub/stratumv2/scripts/results/confidence_eval/after_repair.jsonl")
RESULTS_DIR      = Path("D:/GitHub/stratumv2/scripts/results/selfheal_quality")
JUDGE_MODEL      = "gpt-4o"

# The 4 low-confidence question IDs
LOW_CONF_IDS = {"django-005", "django-011", "django-016", "django-017"}

# ── Load pre-repair answers ────────────────────────────────────────────────
def load_before_answers() -> dict[str, dict]:
    results = {}
    for line in CONFIDENCE_RAW.read_text().splitlines():
        row = json.loads(line)
        if row["id"] in LOW_CONF_IDS:
            results[row["id"]] = row
    return results

# ── Re-run questions post-repair ───────────────────────────────────────────
async def _init_state(repo_path: Path) -> None:
    """Mirror the init pattern from benchmark.py."""
    import asyncio as _asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from provenant.core.persistence.database import init_db, resolve_db_url
    from provenant.core.persistence.search import FullTextSearch
    from provenant.core.persistence.vector_store import InMemoryVectorStore
    from provenant.core.workspace.registry import RepoContext
    from provenant.llm.providers.embedding.base import MockEmbedder
    from provenant.server.mcp_server import _state

    if not hasattr(RepoContext, "repo_path"):
        RepoContext.repo_path = property(lambda self: str(self.path))

    _state._repo_path = str(repo_path)
    db_url = resolve_db_url(str(repo_path))
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_async_engine(db_url, connect_args=connect_args)
    await init_db(engine)
    _state._session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    _state._fts = FullTextSearch(engine)
    await _state._fts.ensure_index()
    _state._vector_store_ready = _asyncio.Event()
    _state._vector_store = InMemoryVectorStore(embedder=MockEmbedder())
    _state._vector_store_ready.set()
    print(f"  State initialised for {repo_path.name}")


async def get_after_answers(before: dict[str, dict]) -> dict[str, dict]:
    """Run the same questions through Provenant (uses repaired wiki)."""
    from provenant.server.mcp_server.tool_answer import stratum_ask as get_answer

    await _init_state(DJANGO_REPO)

    after = {}
    for qid, row in before.items():
        question = row["question"]
        print(f"  Re-running {qid}: {question[:60]}…")
        try:
            result = await get_answer(question=question, compress=True, force_synthesize=True, hyde=False)
            answer  = result.get("answer", "")
            cites   = result.get("citations", [])
            conf    = len(cites) / 5 if cites else 0.0
            after[qid] = {"id": qid, "question": question,
                          "answer": answer, "confidence_after": conf}
            print(f"    conf_after={conf:.2f}  answer_len={len(answer)}")
        except Exception as exc:
            print(f"    ERROR: {exc}")
            after[qid] = {"id": qid, "question": question,
                          "answer": f"[error: {exc}]", "confidence_after": 0.0}
    return after

# ── OpenAI judge ───────────────────────────────────────────────────────────
def judge_pair(question: str, answer_a: str, answer_b: str,
               label_a: str = "Before repair", label_b: str = "After repair") -> dict:
    """Ask GPT-4o-mini to score both answers 1-5."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.openai.com/v1")

    prompt = f"""You are evaluating two answers to a software engineering question.
Score each answer from 1 to 5 based on accuracy, completeness, and clarity.
5 = excellent, 4 = good, 3 = acceptable, 2 = poor, 1 = wrong/missing.

Question: {question}

Answer A ({label_a}):
{answer_a[:2000]}

Answer B ({label_b}):
{answer_b[:2000]}

Respond with ONLY valid JSON: {{"score_a": <int>, "score_b": <int>, "reasoning": "<one sentence>"}}"""

    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=120,
    )
    text = resp.choices[0].message.content.strip()
    try:
        return json.loads(text)
    except Exception:
        import re
        sa = re.search(r'"score_a"\s*:\s*(\d)', text)
        sb = re.search(r'"score_b"\s*:\s*(\d)', text)
        return {"score_a": int(sa.group(1)) if sa else 0,
                "score_b": int(sb.group(1)) if sb else 0,
                "reasoning": text}

# ── Main ──────────────────────────────────────────────────────────────────
async def main():
    if not OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY not set")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading pre-repair answers…")
    before = load_before_answers()
    print(f"  {len(before)} questions found: {sorted(before)}")

    print("\nRe-running questions with repaired wiki (post-repair)…")
    after = await get_after_answers(before)

    print("\nJudging before vs after with GPT-4o-mini…")
    rows = []
    for qid in sorted(LOW_CONF_IDS):
        if qid not in before or qid not in after:
            print(f"  Skipping {qid} (missing data)")
            continue
        q      = before[qid]["question"]
        ans_b  = before[qid].get("answer", "")
        ans_a  = after[qid].get("answer", "")
        conf_b = before[qid].get("attribution_confidence", 0.0)
        conf_a = after[qid].get("confidence_after", 0.0)

        print(f"  Judging {qid}: {q[:55]}…")
        scores = judge_pair(q, ans_b, ans_a)
        row = {
            "id":            qid,
            "question":      q,
            "conf_before":   conf_b,
            "conf_after":    conf_a,
            "delta_conf":    round(conf_a - conf_b, 2),
            "score_before":  scores["score_a"],
            "score_after":   scores["score_b"],
            "delta_quality": scores["score_b"] - scores["score_a"],
            "reasoning":     scores.get("reasoning", ""),
        }
        rows.append(row)
        print(f"    quality: {scores['score_a']} -> {scores['score_b']}  "
              f"(delta={row['delta_quality']:+d})  conf: {conf_b:.2f} -> {conf_a:.2f}")

    # ── Save ──────────────────────────────────────────────────────────────
    out_path = RESULTS_DIR / "selfheal_quality.jsonl"
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("Self-Healing Quality — Before vs After Repair")
    print(f"{'Query':<20} {'Conf B':>6} {'Conf A':>6} {'dConf':>6}  {'Q-B':>4} {'Q-A':>4} {'dQ':>4}")
    print("-"*60)
    for r in rows:
        label = r["id"]
        print(f"{label:<20} {r['conf_before']:>6.2f} {r['conf_after']:>6.2f} "
              f"{r['delta_conf']:>+6.2f}  {r['score_before']:>4} {r['score_after']:>4} {r['delta_quality']:>+4}")

    avg_dq = sum(r["delta_quality"] for r in rows) / len(rows) if rows else 0
    avg_dc = sum(r["delta_conf"]    for r in rows) / len(rows) if rows else 0
    print("-"*60)
    print(f"{'Average':<20} {'':>6} {'':>6} {avg_dc:>+6.2f}  {'':>4} {'':>4} {avg_dq:>+4.1f}", flush=True)
    print(f"\nResults saved to {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
