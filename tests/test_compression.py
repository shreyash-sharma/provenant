from provenant.core.compression.attribute import score_pages
from provenant.core.compression.evaluate import format_compression_stats
from provenant.core.compression.prune import prune_pages


def test_prune_removes_zero_score():
    pages = [
        {
            "path": "auth.py",
            "title": "Auth",
            "content": "authenticate validate_token",
            "symbols": ["authenticate"],
        },
        {
            "path": "utils.py",
            "title": "Utils",
            "content": "format helper",
            "symbols": ["format_bytes"],
        },
        {
            "path": "db.py",
            "title": "DB",
            "content": "query connect",
            "symbols": ["query"],
        },
    ]
    answer = "The authenticate function in auth.py handles JWT validation."
    scores = score_pages(pages, answer, import_graph={}, cited_paths=["auth.py"])
    result = prune_pages(pages, scores, threshold=0.05, min_keep=1)
    kept_paths = [p["path"] for p in result.kept_pages]
    assert "auth.py" in kept_paths
    assert result.compression_ratio >= 0.0
    stats = format_compression_stats(result)
    assert "compression" in stats
    assert stats["compression"]["initial_files"] == 3


def test_citation_score():
    from provenant.core.compression.attribute import citation_score

    assert (
        citation_score(
            "auth.py",
            ["authenticate", "validate_token"],
            "The authenticate function handles JWT.",
        )
        == 1.0
    )
    assert (
        citation_score(
            "utils.py",
            ["format_bytes"],
            "The authenticate function handles JWT.",
        )
        == 0.0
    )


def test_compression_ratio():
    from provenant.core.compression.evaluate import format_compression_stats
    from provenant.core.compression.models import CompressionResult

    r = CompressionResult([], [], 10, 4, 10000, 4000, 0.6, [])
    stats = format_compression_stats(r)
    assert stats["compression"]["compression_pct"] == 60.0
