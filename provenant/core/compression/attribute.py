def citation_score(page_path: str, page_symbols: list[str], answer: str) -> float:
    """1.0 if page path stem or any of its symbols appear in the answer, else 0.0."""
    from pathlib import Path

    stem = Path(page_path).stem.lower()
    answer_lower = answer.lower()
    if stem in answer_lower:
        return 1.0
    if Path(page_path).name.lower() in answer_lower:
        return 1.0
    for sym in page_symbols:
        if sym.lower() in answer_lower:
            return 1.0
    return 0.0


def structural_score(
    page_path: str,
    cited_paths: list[str],
    import_graph: dict[str, list[str]],
) -> float:
    """
    1.0 if page is a direct dependency of a cited file.
    0.5 if a cited file depends on this page.
    0.0 otherwise.
    """
    for cited in cited_paths:
        deps = import_graph.get(cited, [])
        if any(page_path in d for d in deps):
            return 1.0
    for cited in cited_paths:
        page_deps = import_graph.get(page_path, [])
        if any(cited in d for d in page_deps):
            return 0.5
    return 0.0


def score_pages(
    pages: list[dict],
    answer: str,
    import_graph: dict[str, list[str]],
    cited_paths: list[str],
) -> list["PageScore"]:
    """Score all retrieved pages. Returns PageScore list sorted by final_score desc."""
    from provenant.core.compression.models import PageScore

    results = []
    for page in pages:
        c = citation_score(page["path"], page.get("symbols", []), answer)
        s = structural_score(page["path"], cited_paths, import_graph)
        final = c * 0.6 + s * 0.4
        results.append(
            PageScore(
                path=page["path"],
                title=page.get("title", ""),
                content_preview=page.get("content", "")[:200],
                citation_score=c,
                structural_score=s,
                final_score=final,
            )
        )
    results.sort(key=lambda x: x.final_score, reverse=True)
    return results
