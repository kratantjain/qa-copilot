from __future__ import annotations

import requests

from ..log import log
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
        self.last_stats: dict = {}

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
        self._log_stats(data)
        text = (data.get("message") or {}).get("content", "")
        if not text.strip():
            raise LLMError("Ollama returned an empty response.")
        return text

    def _log_stats(self, data: dict) -> None:
        """Log Ollama's own timings so slow runs can be diagnosed (load vs prompt vs generation)."""
        ns = 1e9
        gen, gen_s = data.get("eval_count", 0), data.get("eval_duration", 0) / ns
        self.last_stats = {
            "load_s": data.get("load_duration", 0) / ns,
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "prompt_s": data.get("prompt_eval_duration", 0) / ns,
            "gen_tokens": gen, "gen_s": gen_s,
            "gen_tps": gen / gen_s if gen_s else 0.0,
            "total_s": data.get("total_duration", 0) / ns,
        }
        st = self.last_stats
        log.info("ollama: load %.1fs | prompt %d tok in %.1fs | generated %d tok in %.1fs "
                 "(%.1f tok/s) | total %.1fs", st["load_s"], st["prompt_tokens"], st["prompt_s"],
                 gen, gen_s, st["gen_tps"], st["total_s"])

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
