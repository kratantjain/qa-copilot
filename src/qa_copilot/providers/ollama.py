from __future__ import annotations

import requests

from .base import LLMError, Provider


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", **kw):
        super().__init__(model, **kw)
        self.base_url = base_url.rstrip("/")

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> str:
        try:
            r = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": "json",
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": prompt}],
                    "options": {"temperature": self.temperature, "num_predict": max_tokens,
                                "num_ctx": 8192},
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except requests.Timeout as e:
            raise LLMError("Ollama timed out - is the model loaded?") from e
        except requests.RequestException as e:
            raise LLMError(f"Could not reach Ollama at {self.base_url}: {e}") from e
        if data.get("done_reason") == "length":
            raise LLMError("Output hit the token limit; JSON is likely truncated.")
        text = (data.get("message") or {}).get("content", "")
        if not text.strip():
            raise LLMError("Ollama returned an empty response.")
        return text

    def health(self) -> tuple[bool, str]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            if self.model not in names:
                return False, f"Model '{self.model}' not pulled. Run: ollama pull {self.model}"
            return True, "ok"
        except requests.RequestException as e:
            return False, f"Ollama unreachable: {e}"
