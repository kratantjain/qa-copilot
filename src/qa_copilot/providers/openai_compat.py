from __future__ import annotations

import os

import requests

from .base import LLMError, Provider


class OpenAICompatProvider(Provider):
    """Works with OpenAI and any OpenAI-compatible server (vLLM, LM Studio, Groq...)."""

    name = "openai"

    def __init__(self, model: str, base_url: str = "https://api.openai.com/v1",
                 api_key: str | None = None, **kw):
        super().__init__(model, **kw)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    def complete(self, system: str, prompt: str, max_tokens: int = 2048,
                 schema: dict | None = None) -> str:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions", headers=headers,
                json={"model": self.model, "temperature": self.temperature,
                      "max_tokens": max_tokens,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}]},
                timeout=self.timeout,
            )
            if r.status_code >= 400:
                raise LLMError(f"OpenAI-compatible API error {r.status_code}: {r.text[:300]}")
            text = r.json()["choices"][0]["message"]["content"] or ""
        except requests.RequestException as e:
            raise LLMError(f"Request failed: {e}") from e
        except (KeyError, IndexError) as e:
            raise LLMError("Unexpected response shape from API.") from e
        if not text.strip():
            raise LLMError("Empty response from API.")
        return text
