"""Local fastembed embedder — no API key, no PyTorch required.

Uses ONNX Runtime under the hood: ~40 MB total install, no CUDA dependencies.
Install: pip install fastembed
"""

from __future__ import annotations

import asyncio

_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_DEFAULT_DIMS = 384


class LocalEmbedder:
    """fastembed-backed embedder implementing the provenant Embedder protocol.

    Lazy-loads the model on first embed() call so import is free.
    Runs encode() in a thread pool to avoid blocking the asyncio event loop.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: object | None = None

    @property
    def dimensions(self) -> int:
        _dims: dict[str, int] = {
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-base-en-v1.5": 768,
            "BAAI/bge-large-en-v1.5": 1024,
            "sentence-transformers/all-MiniLM-L6-v2": 384,
        }
        return _dims.get(self._model_name, _DEFAULT_DIMS)

    def _get_model(self) -> object:
        if self._model is None:
            from fastembed import TextEmbedding  # type: ignore[import-untyped]
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def warmup(self) -> None:
        """Download and load the model synchronously. Call once during setup to avoid cold-start."""
        self._get_model()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        def _encode() -> list[list[float]]:
            model = self._get_model()
            return [list(v) for v in model.embed(texts)]  # type: ignore[union-attr]

        return await asyncio.to_thread(_encode)
