"""
Calibration eval: does attribution_confidence predict answer quality?

Runs stratum_ask with synthesis on N questions, records confidence score
per question, then judges answer quality. Produces a calibration curve:

    confidence bucket -> (avg quality, n questions)

If the curve is monotonic (high confidence -> high quality), attribution
confidence is a well-calibrated signal and can be used for routing.

Usage:
    python scripts/eval_confidence.py \
        --repo D:/GitHub/swebench_repos/django__django \
        --questions scripts/questions/django.jsonl \
        --output scripts/results/confidence_eval

Outputs:
    scripts/results/confidence_eval/confidence_raw.jsonl
    scripts/results/confidence_eval/calibration.json
    scripts/results/confidence_eval/calibration_summary.txt
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Bootstrap stratum state ──────────────────────────────────────────────────

def _init_stratum_state(repo_path: Path) -> None:
    """Load DB + FTS + vector store into _state."""
    import asyncio as _asyncio
    from provenant.core.persistence import (
        FullTextSearch, create_engine, create_session_factory,
        init_db, resolve_db_url,
    )
    from provenant.server.mcp_server import _state
    from provenant.core.workspace.registry import RepoContext

    # Patch missing property
    if not hasattr(RepoContext, "repo_path"):
        RepoContext.repo_path = property(lambda self: str(self.path))

    async def _setup():
        engine = create_engine(resolve_db_url(repo_path))
        await init_db(engine)
        sf = create_session_factory(engine)
        _state._repo_path = str(repo_path)
        _state._session_factory = sf
        _state._fts = FullTextSearch(engine)
        await _state._fts.ensure_index()

        # Load LanceDB vector store
        _state._vector_store_ready = _asyncio.Event()
        try:
            from provenant.core.persistence.vector_store import LanceDBVectorStore
            from provenant.cli.commands.init_cmd import _resolve_embedder
            embedder_name = _resolve_embedder(None)
            if embedder_name == "local":
                from provenant.llm.providers.embedding.local import LocalEmbedder
                embedder = LocalEmbedder()
            else:
                from provenant.llm.providers.embedding.base import MockEmbedder
                embedder = MockEmbedder()
            lance_dir = repo_path / ".provenant" / "lancedb"
            if lance_dir.exists():
                vs = LanceDBVectorStore(str(lance_dir), embedder=embedder)
                _state._vector_store = vs
                print(f"  Vector store: LanceDB loaded")
            else:
                from provenant.core.persistence.vector_store import InMemoryVectorStore
                _state._vector_store = InMemoryVectorStore(embedder=embedder)
                print(f"  Vector store: in-memory (no LanceDB)")
        except Exception as e:
            from provenant.core.persistence import InMemoryVectorStore
            from provenant.llm.providers.embedding.base import MockEmbedder
            _state._vector_store = InMemoryVectorStore(embedder=MockEmbedder())
            print(f"  Vector store: fallback ({e})")
        _state._vector_store_ready.set()

        from provenant.core.persistence import InMemoryVectorStore
        from provenant.llm.providers.embedding.base import MockEmbedder
        _state._decision_store = InMemoryVectorStore(embedder=MockEmbedder())

    _asyncio.run(_setup())
    print("State initialized.\n")


# ── Single question runner ────────────────────────────────────────────────────

async def _run_question(question: str) -> dict:
    from provenant.server.mcp_server.tool_answer import stratum_ask
    t0 = time.monotonic()
    result = await stratum_ask(question=question, force_synthesize=True, hyde=True)
    elapsed_ms = (time.monotonic() - t0) * 1000

    answer = result.get("answer", "")
    citations = result.get("citations", [])
    fallback = result.get("fallback_targets", [])
    confidence_label = result.get("confidence", "low")
    attribution_confidence = result.get("attribution_confidence", 0.0)
    tokens_in = result.get("_meta", {}).get("tokens_in", 0) or 0
    hyde_used = result.get("_meta", {}).get("hyde_used", False)

    return {
        "answer": answer,
        "citations": citations,
        "fallback_targets": fallback,
        "confidence_label": confidence_label,
        "attribution_confidence": attribution_confidence,
        "tokens_in": tokens_in,
        "elapsed_ms": round(elapsed_ms),
        "hyde_used": hyde_used,
    }


# ── Judge ─────────────────────────────────────────────────────────────────────

def _judge_answer(client, question: str, answer: str) -> int:
    """Score answer 1-5 using LLM judge. Returns 3 on error."""
    system = (
        "You are an expert Python developer evaluating answers about Django. "
        "Score the answer 1-5 for accuracy and completeness.\n"
        "5=perfect, 4=good with minor gaps, 3=adequate but vague, "
        "2=significant gaps, 1=wrong or unhelpful.\n"
        "Return ONLY valid JSON: {\"score\": <int>, \"reason\": \"<one sentence>\"}"
    )
    prompt = f"Question: {question}\n\nAnswer:\n{answer or '(no answer)'}\n\nScore 1-5. JSON only."
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=os.environ.get("JUDGE_MODEL", "deepseek-v3.2"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=100,
            )
            data = json.loads(resp.choices[0].message.content)
            return int(data.get("score", 3))
        except Exception as e:
            if attempt == 2:
                print(f"    judge error: {e}")
                return 3
            time.sleep(1)
    return 3


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--output", default="scripts/results/confidence_eval")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM quality scoring")
    args = parser.parse_args()

    repo_path = Path(args.repo)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    questions = [json.loads(l) for l in open(args.questions) if l.strip()]
    print(f"Questions: {len(questions)}")
    print(f"Repo: {repo_path}")
    print(f"Output: {out_dir}\n")

    _init_stratum_state(repo_path)

    import openai
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    judge_client = openai.OpenAI(api_key=api_key, base_url=base_url)

    raw_path = out_dir / "confidence_raw.jsonl"
    results = []

    with open(raw_path, "w") as f:
        for i, q in enumerate(questions, 1):
            qid = q["id"]
            question = q["question"]
            print(f"[{i}/{len(questions)}] {qid}: {question[:60]}...")

            # Run synthesis
            row = asyncio.run(_run_question(question))

            # Judge quality
            quality_score = 3
            if not args.no_judge and row["answer"]:
                quality_score = _judge_answer(judge_client, question, row["answer"])

            record = {
                "id": qid,
                "question": question,
                "answer": row["answer"],
                "citations": row["citations"],
                "fallback_targets": row["fallback_targets"],
                "confidence_label": row["confidence_label"],
                "attribution_confidence": row["attribution_confidence"],
                "quality_score": quality_score,
                "tokens_in": row["tokens_in"],
                "elapsed_ms": row["elapsed_ms"],
                "hyde_used": row["hyde_used"],
            }
            results.append(record)
            f.write(json.dumps(record) + "\n")
            f.flush()

            print(
                f"    attr_conf={row['attribution_confidence']:.2f}  "
                f"label={row['confidence_label']}  "
                f"quality={quality_score}/5  "
                f"tokens={row['tokens_in']}  "
                f"hyde={'yes' if row['hyde_used'] else 'no'}"
            )

    # ── Calibration analysis ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("CALIBRATION ANALYSIS")
    print(f"{'='*60}")

    # Bucket by attribution_confidence
    buckets = {"0.0-0.2": [], "0.2-0.4": [], "0.4-0.6": [], "0.6-0.8": [], "0.8-1.0": []}
    for r in results:
        c = r["attribution_confidence"]
        if c < 0.2:
            buckets["0.0-0.2"].append(r)
        elif c < 0.4:
            buckets["0.2-0.4"].append(r)
        elif c < 0.6:
            buckets["0.4-0.6"].append(r)
        elif c < 0.8:
            buckets["0.6-0.8"].append(r)
        else:
            buckets["0.8-1.0"].append(r)

    print(f"\n{'Confidence':12} {'N':>4} {'Avg Quality':>12} {'Avg Tokens':>12}")
    print("-" * 44)
    calibration = {}
    for bucket_name, bucket_rows in buckets.items():
        if not bucket_rows:
            continue
        avg_q = sum(r["quality_score"] for r in bucket_rows) / len(bucket_rows)
        avg_t = sum(r["tokens_in"] for r in bucket_rows) / len(bucket_rows)
        print(f"{bucket_name:12} {len(bucket_rows):>4} {avg_q:>12.2f} {avg_t:>12.0f}")
        calibration[bucket_name] = {
            "n": len(bucket_rows),
            "avg_quality": round(avg_q, 3),
            "avg_tokens": round(avg_t),
        }

    # Overall stats
    all_conf = [r["attribution_confidence"] for r in results]
    all_qual = [r["quality_score"] for r in results]
    avg_conf = sum(all_conf) / len(all_conf)
    avg_qual = sum(all_qual) / len(all_qual)
    low_conf = sum(1 for c in all_conf if c < 0.4)

    print(f"\nOverall: avg_confidence={avg_conf:.2f}  avg_quality={avg_qual:.2f}")
    print(f"Low confidence (<0.4): {low_conf}/{len(results)} queries -> repair candidates")

    # Correlation (Pearson r)
    if len(results) > 2:
        mean_c = avg_conf
        mean_q = avg_qual
        cov = sum((r["attribution_confidence"] - mean_c) * (r["quality_score"] - mean_q)
                  for r in results) / len(results)
        std_c = (sum((r["attribution_confidence"] - mean_c)**2 for r in results) / len(results))**0.5
        std_q = (sum((r["quality_score"] - mean_q)**2 for r in results) / len(results))**0.5
        if std_c > 0 and std_q > 0:
            pearson_r = cov / (std_c * std_q)
            print(f"Pearson r (confidence vs quality): {pearson_r:.3f}")
        else:
            pearson_r = 0.0
    else:
        pearson_r = 0.0

    # Save calibration
    calibration_out = {
        "n": len(results),
        "avg_confidence": round(avg_conf, 3),
        "avg_quality": round(avg_qual, 3),
        "low_confidence_count": low_conf,
        "low_confidence_pct": round(low_conf / len(results) * 100, 1),
        "pearson_r": round(pearson_r, 3),
        "buckets": calibration,
        "low_confidence_questions": [
            {"id": r["id"], "confidence": r["attribution_confidence"],
             "quality": r["quality_score"], "question": r["question"][:100]}
            for r in sorted(results, key=lambda x: x["attribution_confidence"])[:5]
        ],
    }
    with open(out_dir / "calibration.json", "w") as f:
        json.dump(calibration_out, f, indent=2)

    # Summary text
    summary = f"""# Confidence Calibration Results — {repo_path.name}

## Overall
- Questions: {len(results)}
- Avg attribution confidence: {avg_conf:.2f}
- Avg quality score: {avg_qual:.2f}/5
- Low confidence queries (<0.4): {low_conf} ({low_conf/len(results):.0%}) -> repair candidates
- Pearson r (confidence vs quality): {pearson_r:.3f}

## Calibration Curve
| Confidence | N | Avg Quality |
|-----------|---|-------------|
"""
    for bucket_name, stats in calibration.items():
        summary += f"| {bucket_name} | {stats['n']} | {stats['avg_quality']:.2f}/5 |\n"

    summary += f"""
## Interpretation
{"✅ Confidence is a strong predictor of quality (r > 0.5)" if pearson_r > 0.5
 else "⚠️  Confidence is a moderate predictor" if pearson_r > 0.2
 else "❌ Weak correlation — confidence signal needs tuning"}

## Repair candidates (lowest confidence)
"""
    for r in sorted(results, key=lambda x: x["attribution_confidence"])[:5]:
        summary += f"- [{r['attribution_confidence']:.2f}] {r['id']}: {r['question'][:80]}\n"

    with open(out_dir / "calibration_summary.txt", "w") as f:
        f.write(summary)

    print(f"\nResults: {raw_path}")
    print(f"Calibration: {out_dir / 'calibration.json'}")
    print(f"Summary: {out_dir / 'calibration_summary.txt'}")


if __name__ == "__main__":
    main()
