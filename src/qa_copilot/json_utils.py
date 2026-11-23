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


def salvage_json(text: str) -> dict:
    """Recover the complete items from truncated JSON by closing open brackets.

    Tries progressively earlier cut points (just after a ``}``) until the repaired text parses.
    """
    start = text.find("{")
    if start == -1:
        raise LLMError("No JSON to salvage.")
    text = text[start:]
    cuts = [i + 1 for i, ch in enumerate(text) if ch == "}"]
    for cut in reversed(cuts[-40:]):
        head, stack, in_str, esc = text[:cut], [], False, False
        for ch in head:
            if in_str:
                esc = (ch == "\\") and not esc
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append("}" if ch == "{" else "]")
            elif ch in "}]" and stack:
                stack.pop()
        if in_str:
            continue
        try:
            data = json.loads(re.sub(r",\s*$", "", head) + "".join(reversed(stack)))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise LLMError("Could not salvage truncated JSON.")
