from __future__ import annotations

import requests

from .base import LLMError, Provider


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", num_ctx: int = 4096,
                 keep_alive: str = "30m", use_schema: bool = True, **kw):
        super().__init__(model, **kw)
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.use_schema = use_schema

    def _post(self, system: str, prompt: str, max_tokens: int, fmt) -> requests.Response:
        return requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "format": fmt,
                "keep_alive": self.keep_alive,  # keep the model loaded between calls
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt}],
                "options": {"temperature": self.temperature, "num_predict": max_tokens,
                            "num_ctx": self.num_ctx},
            },
            timeout=self.timeout,
        )

    def complete(self, system: str, prompt: str, max_tokens: int = 2048,
                 schema: dict | None = None) -> str:
        try:
            r = self._post(system, prompt, max_tokens, schema if (schema and self.use_schema) else "json")
            if r.status_code in (400, 500) and schema and self.use_schema:
                # Older/odd Ollama builds may reject schema-constrained output: fall back.
                r = self._post(system, prompt, max_tokens, "json")
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
