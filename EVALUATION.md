# Evaluation

Provenant was evaluated on SWE-bench Verified: 500 real GitHub issues across 12 Python repositories.

## What was measured

- File Coverage@5
- File Coverage@10
- Mean reciprocal rank (MRR)
- Token reduction versus naive repo/file reading
- Answer quality using an LLM judge
- Low-confidence query repair rate
- Cost per repair cycle

## Results

| Metric | Baseline | Provenant | Delta |
|---|---:|---:|---:|
| File Coverage@5, wiki BM25 | 56.2% | 63.8% | +7.6 pp |
| File Coverage@5, reranker + selective HyDE | 56.2% | 66.2% | +10.0 pp |
| File Coverage@10, reranker + selective HyDE | 69.0% | 75.2% | +6.2 pp |
| MRR, reranker + selective HyDE | 0.404 | 0.454 | +0.050 |
| Token reduction | baseline | 60-65x lower | - |
| Answer quality | baseline | parity | -0.15/5 avg delta |
| Low-confidence repair | 4 low-confidence queries | 2 improved | avg judge 4.50 -> 4.75 |
| Cost per repair cycle | - | ~$0.02 | 10 pages repaired / 1,393 |

## Notes

- File-localization results use 500 SWE-bench Verified tasks across 12 Python repositories.
- Per-repo breakdowns report the 9 repositories with at least 10 tasks; 3 smaller repositories are omitted from per-repo tables for statistical reliability.
- Token reduction was measured on Flask and Django question-answering workloads. Flask used 1,070 wiki tokens versus 69,044 naive source tokens (64.5x). Django used 994 wiki tokens versus 59,634 naive source tokens (60.0x).
- Attribution confidence is `cited_pages / retrieved_pages`; in the Django study, confidence correlated with answer quality at Pearson r = 0.415.

## Reproducibility

Summary artifacts are in [`benchmarks/`](benchmarks/). Full benchmark details are described in the whitepaper:
[Provenant whitepaper](https://www.shreyashsharma.com/writing/provenant)

A longer research manuscript is currently under submission.
