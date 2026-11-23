from __future__ import annotations

import os

import requests

from .base import LLMError, Provider


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None, **kw):
        super().__init__(model, **kw)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")

    def complete(self, system: str, prompt: str, max_tokens: int = 2048,
                 schema: dict | None = None) -> str:
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set.")
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": self.model, "max_tokens": max_tokens,
                      "temperature": self.temperature, "system": system,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=self.timeout,
            )
            if r.status_code >= 400:
                raise LLMError(f"Anthropic API error {r.status_code}: {r.text[:300]}")
            blocks = r.json().get("content", [])
        except requests.RequestException as e:
            raise LLMError(f"Anthropic request failed: {e}") from e
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        if not text.strip():
            raise LLMError("Anthropic returned an empty response.")
        return text
