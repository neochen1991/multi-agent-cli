"""Output truncation utilities."""

from __future__ import annotations

from typing import Any, Dict


def truncate_text(value: str, *, max_chars: int = 2400) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...(truncated,{len(text)} chars)"


def truncate_payload(payload: Dict[str, Any], *, max_chars: int = 1800) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if isinstance(value, str):
            result[key] = truncate_text(value, max_chars=max_chars)
        elif isinstance(value, list):
            result[key] = value[:20]
        else:
            result[key] = value
    return result

