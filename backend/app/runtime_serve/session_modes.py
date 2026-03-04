"""Session mode policy helpers for runtime serving layer."""

from __future__ import annotations

from enum import Enum


class DebateExecutionMode(str, Enum):
    STANDARD = "standard"
    QUICK = "quick"
    BACKGROUND = "background"
    ASYNC = "async"


def normalize_execution_mode(raw: str | None) -> DebateExecutionMode:
    text = str(raw or "").strip().lower()
    if text == DebateExecutionMode.QUICK.value:
        return DebateExecutionMode.QUICK
    if text == DebateExecutionMode.BACKGROUND.value:
        return DebateExecutionMode.BACKGROUND
    if text == DebateExecutionMode.ASYNC.value:
        return DebateExecutionMode.ASYNC
    return DebateExecutionMode.STANDARD


__all__ = ["DebateExecutionMode", "normalize_execution_mode"]
