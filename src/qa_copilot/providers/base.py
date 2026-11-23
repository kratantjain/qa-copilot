from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    """Raised for any provider failure (network, auth, bad output)."""


class LLMTruncated(LLMError):
    """The model hit the token limit; ``text`` holds the partial output."""

    def __init__(self, message: str, text: str = ""):
        super().__init__(message)
        self.text = text


class Provider(ABC):
    name = "base"

    def __init__(self, model: str, timeout: int = 600, temperature: float = 0.1):
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    @abstractmethod
    def complete(self, system: str, prompt: str, max_tokens: int = 2048,
                 schema: dict | None = None) -> str:
        """Return the raw text completion (expected to contain JSON).

        ``schema`` is an optional JSON schema that providers may use to constrain output.
        """

    def health(self) -> tuple[bool, str]:
        return True, "ok"
