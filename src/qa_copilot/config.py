"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    provider: str = field(default_factory=lambda: os.getenv("QA_COPILOT_PROVIDER", "ollama"))
    model: str = field(default_factory=lambda: os.getenv("QA_COPILOT_MODEL", ""))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
    openai_base_url: str = field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    timeout: int = field(default_factory=lambda: int(os.getenv("QA_COPILOT_TIMEOUT", "600")))
    temperature: float = 0.1
    num_ctx: int = field(default_factory=lambda: int(os.getenv("QA_COPILOT_NUM_CTX", "4096")))
    ollama_schema: bool = field(
        default_factory=lambda: os.getenv("QA_COPILOT_OLLAMA_SCHEMA", "0") == "1")
    db_path: str = field(default_factory=lambda: os.getenv("QA_COPILOT_DB", ".qa_copilot/history.db"))

    DEFAULT_MODELS = {
        "ollama": "qwen2.5:3b",
        "anthropic": "claude-sonnet-4-5",
        "openai": "gpt-4o-mini",
        "mock": "mock",
    }

    @property
    def resolved_model(self) -> str:
        return self.model or self.DEFAULT_MODELS.get(self.provider, "")
