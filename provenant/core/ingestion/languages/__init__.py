"""Centralised language configuration for provenant.

Public API::

    from provenant.core.ingestion.languages import REGISTRY

    spec = REGISTRY.get("python")
    ext_map = REGISTRY.all_extensions()
    code = REGISTRY.code_languages()
"""

from .registry import REGISTRY
from .spec import LanguageSpec

__all__ = ["REGISTRY", "LanguageSpec"]
