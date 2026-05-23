from provenant.core.compression.models import CompressionResult, PageScore


def prune_pages(
    pages: list[dict],
    scores: list[PageScore],
    threshold: float = 0.05,
    min_keep: int = 1,
) -> CompressionResult:
    """
    Remove pages with final_score below threshold.
    Always keep at least min_keep pages.
    Pages with score == 0.0 and citation_score == 0.0 are pruned first.
    """
    initial_count = len(pages)
    initial_chars = sum(len(p.get("content", "")) for p in pages)

    scored_map = {s.path: s for s in scores}
    kept = []
    pruned = []

    sorted_pages = sorted(
        pages,
        key=lambda p: scored_map.get(p["path"], PageScore("", "", "", 0, 0, 0)).final_score,
        reverse=True,
    )

    for i, page in enumerate(sorted_pages):
        score = scored_map.get(page["path"])
        if score is None:
            kept.append(page)
            continue
        if i < min_keep:
            score.kept = True
            score.reason = "min_keep"
            kept.append(page)
        elif score.final_score >= threshold:
            score.kept = True
            score.reason = "cited" if score.citation_score > 0 else "structural"
            kept.append(page)
        else:
            score.kept = False
            score.reason = "pruned"
            pruned.append(score)

    final_chars = sum(len(p.get("content", "")) for p in kept)
    initial_chars = max(initial_chars, 1)
    compression_ratio = (initial_chars - final_chars) / initial_chars

    return CompressionResult(
        kept_pages=kept,
        pruned_pages=pruned,
        initial_count=initial_count,
        final_count=len(kept),
        initial_chars=initial_chars,
        final_chars=final_chars,
        compression_ratio=compression_ratio,
        misleading_paths=[],
    )
