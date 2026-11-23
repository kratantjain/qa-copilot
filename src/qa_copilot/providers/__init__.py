from __future__ import annotations

from ..config import Settings
from .anthropic import AnthropicProvider
from .base import LLMError, Provider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

PROVIDERS = ("ollama", "anthropic", "openai", "mock")


def get_provider(settings: Settings | None = None) -> Provider:
    s = settings or Settings()
    kw = dict(timeout=s.timeout, temperature=s.temperature)
    model = s.resolved_model
    if s.provider == "ollama":
        return OllamaProvider(model, base_url=s.ollama_url, **kw)
    if s.provider == "anthropic":
        return AnthropicProvider(model, **kw)
    if s.provider == "openai":
        return OpenAICompatProvider(model, base_url=s.openai_base_url, **kw)
    if s.provider == "mock":
        return MockProvider(model, **kw)
    raise LLMError(f"Unknown provider '{s.provider}'. Choose from: {', '.join(PROVIDERS)}")


__all__ = ["get_provider", "Provider", "LLMError", "MockProvider", "PROVIDERS"]
