"""provenant provider package.

Sub-packages:
    llm/       — LLM providers (Anthropic, OpenAI, OpenRouter, Gemini, Ollama, LiteLLM)
    embedding/ — Embedding providers (OpenAI, Gemini, Mock)

Preferred entry points:

    from provenant.llm.providers.llm import get_provider
    from provenant.llm.providers.embedding import get_embedder

    provider = get_provider("openai", api_key="sk-...", model="gpt-5.4-nano")
    response = await provider.generate(system_prompt="...", user_prompt="...")

    embedder = get_embedder("openai", api_key="sk-...")
    vectors = await embedder.embed(["text to embed"])

Backward-compatible imports still work:
    from provenant.llm.providers import get_provider  # → llm.registry
"""

from provenant.llm.providers.llm.base import (
    BaseProvider,
    ChatProvider,
    ChatStreamEvent,
    ChatToolCall,
    GeneratedResponse,
    ProviderError,
    RateLimitError,
)
from provenant.llm.providers.llm.registry import get_provider, list_providers, register_provider
from provenant.llm.providers.embedding import get_embedder, list_embedders, register_embedder

__all__ = [
    # LLM
    "BaseProvider",
    "ChatProvider",
    "ChatStreamEvent",
    "ChatToolCall",
    "GeneratedResponse",
    "ProviderError",
    "RateLimitError",
    "get_provider",
    "list_providers",
    "register_provider",
    # Embedding
    "get_embedder",
    "list_embedders",
    "register_embedder",
]
