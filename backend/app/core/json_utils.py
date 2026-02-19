"""
JSON extraction helpers.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Optional


def _iter_json_candidates(text: str) -> Iterable[str]:
    raw = (text or "").strip()
    if not raw:
        return

    # 1) Whole text.
    yield raw

    # 2) Code fences.
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE):
        candidate = block.strip()
        if candidate:
            yield candidate

    # 3) Balanced {...} slices (handles extra prose before/after JSON).
    n = len(raw)
    for start in range(n):
        if raw[start] != "{":
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, n):
            ch = raw[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    yield raw[start : i + 1]
                    break


def extract_json_dict(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first valid JSON object from model output text."""
    for candidate in _iter_json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None

