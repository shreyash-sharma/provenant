"""
Judge: compress=True (no_hyde) vs compress=False (baseline).
Both have nearly identical token counts — delta isolates compression quality effect.
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import openai

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "deepseek-v3.2")

SYSTEM = (
    "You are an expert code documentation evaluator. "
    "Given a developer question and two answers about a codebase, "
    "score each independently on accuracy and completeness (1-5). "
    "5=perfect, 4=good, 3=adequate, 2=poor, 1=wrong. "
    "Return ONLY valid JSON: {\"score_A\": <int>, \"score_B\": <int>, \"reasoning\": \"<one sentence>\"}"
)

USER = "Question: {question}\n\nAnswer A:\n{answer_a}\n\nAnswer B:\n{answer_b}\n\nRate each 1-5. JSON only."


def judge(client, question, a, b):
    for attempt in range(3):
        try:
            r = client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": USER.format(question=question, answer_a=a or "(none)", answer_b=b or "(none)")}],
                temperature=0.0, max_tokens=200,
            )
            d = json.loads(r.choices[0].message.content)
            return int(d.get("score_A", 3)), int(d.get("score_B", 3)), d.get("reasoning", "")
        except Exception as e:
            if attempt == 2:
                return 3, 3, f"error: {e}"
            time.sleep(2)
    return 3, 3, "retries"


def main():
    results_path = Path("scripts/results/benchmark/raw.jsonl")
    out_path = Path("scripts/results/benchmark/judge_compress.jsonl")
    rows = [json.loads(l) for l in open(results_path) if l.strip()]

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    client = openai.OpenAI(api_key=api_key, base_url=base_url)

    print(f"Judging compress=True(no_hyde) vs compress=False(baseline) — {len(rows)} questions")
    print(f"Both modes ~same tokens: isolates compression quality effect\n")

    scored = []
    with open(out_path, "w") as f:
        for i, row in enumerate(rows, 1):
            q = row["question"]
            a_base = row["baseline"].get("answer", "")   # compress=False
            a_comp = row["no_hyde"].get("answer", "")    # compress=True, no HyDE
            tok_base = row["baseline"].get("tokens_in", 0)
            tok_comp = row["no_hyde"].get("tokens_in", 0)

            s_base, s_comp, reason = judge(client, q, a_base, a_comp)
            delta = s_comp - s_base
            winner = "compress" if s_comp > s_base else "baseline" if s_base > s_comp else "tie"

            result = {"id": row["id"], "score_compress": s_comp, "score_baseline": s_base,
                      "delta": delta, "winner": winner, "reasoning": reason,
                      "tokens_compress": tok_comp, "tokens_baseline": tok_base}
            scored.append(result)
            f.write(json.dumps(result) + "\n")
            f.flush()
            print(f"[{i}/{len(rows)}] {row['id']}: compress={s_comp} baseline={s_base} d={delta:+d} {winner.upper()}")

    n = len(scored)
    avg_c = sum(r["score_compress"] for r in scored) / n
    avg_b = sum(r["score_baseline"] for r in scored) / n
    within = sum(1 for r in scored if abs(r["delta"]) <= 0) / n * 100  # exact ties
    within_half = sum(1 for r in scored if abs(r["delta"]) <= 0.5) / n * 100
    wins = sum(1 for r in scored if r["winner"] == "compress")
    ties = sum(1 for r in scored if r["winner"] == "tie")
    losses = sum(1 for r in scored if r["winner"] == "baseline")

    print(f"\n{'='*60}")
    print(f"COMPRESSION QUALITY DELTA (compress=True vs compress=False)")
    print(f"{'='*60}")
    print(f"Avg score — compress=True:  {avg_c:.2f}/5")
    print(f"Avg score — compress=False: {avg_b:.2f}/5")
    print(f"Quality delta:              {avg_c-avg_b:+.2f}")
    print(f"Exact ties:                 {within:.0f}%")
    print(f"Within ±0.5:                {within_half:.0f}%")
    print(f"Compress wins/ties/losses:  {wins}/{ties}/{losses}")
    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
