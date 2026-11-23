"""Tolerant JSON extraction - small local models often wrap or slightly break JSON."""
from __future__ import annotations

import json
import re

from .providers.base import LLMError

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def extract_json(text: str) -> dict:
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Model did not return JSON.") from None
        blob = re.sub(r",\s*([}\]])", r"\1", text[start:end + 1])  # trailing commas
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as e:
            raise LLMError(f"Model returned invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise LLMError("Expected a JSON object.")
    return data
