def format_compression_stats(result: "CompressionResult") -> dict:
    """Returns a dict suitable for adding to MCP tool responses."""
    return {
        "compression": {
            "initial_files": result.initial_count,
            "final_files": result.final_count,
            "files_pruned": result.initial_count - result.final_count,
            "initial_chars": result.initial_chars,
            "final_chars": result.final_chars,
            "compression_ratio": round(result.compression_ratio, 3),
            "compression_pct": round(result.compression_ratio * 100, 1),
            "pruned_files": [p.path for p in result.pruned_pages],
        }
    }
