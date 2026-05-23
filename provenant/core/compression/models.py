from dataclasses import dataclass


@dataclass
class PageScore:
    path: str
    title: str
    content_preview: str
    citation_score: float
    structural_score: float
    final_score: float
    kept: bool = True
    reason: str = ""


@dataclass
class CompressionResult:
    kept_pages: list
    pruned_pages: list[PageScore]
    initial_count: int
    final_count: int
    initial_chars: int
    final_chars: int
    compression_ratio: float
    misleading_paths: list[str]
