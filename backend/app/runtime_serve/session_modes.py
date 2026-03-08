"""Session mode policy helpers for runtime serving layer."""

from __future__ import annotations

from enum import Enum


class DebateExecutionMode(str, Enum):
    """封装DebateExecutionMode相关数据结构或服务能力。"""
    STANDARD = "standard"
    QUICK = "quick"
    BACKGROUND = "background"
    ASYNC = "async"


def normalize_execution_mode(raw: str | None) -> DebateExecutionMode:
    """对输入执行归一化execution模式，将原始数据整理为稳定的内部结构。"""
    text = str(raw or "").strip().lower()
    if text == DebateExecutionMode.QUICK.value:
        return DebateExecutionMode.QUICK
    if text == DebateExecutionMode.BACKGROUND.value:
        return DebateExecutionMode.BACKGROUND
    if text == DebateExecutionMode.ASYNC.value:
        return DebateExecutionMode.ASYNC
    return DebateExecutionMode.STANDARD


__all__ = ["DebateExecutionMode", "normalize_execution_mode"]
