from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    """Raised for any provider failure (network, auth, bad output)."""


class Provider(ABC):
    name = "base"

    def __init__(self, model: str, timeout: int = 600, temperature: float = 0.1):
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    @abstractmethod
    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        """Return the raw text completion (expected to contain JSON)."""

    def health(self) -> tuple[bool, str]:
        return True, "ok"
