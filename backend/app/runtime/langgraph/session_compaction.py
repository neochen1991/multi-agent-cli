"""Session-level compaction helpers."""

from __future__ import annotations

from typing import Any, Dict, List


class SessionCompaction:
    """Compact context/messages before model invocation."""

    @staticmethod
    def compact_messages(messages: List[Dict[str, Any]], *, max_items: int = 14, max_chars: int = 2800) -> List[Dict[str, Any]]:
        """执行压缩messages，控制上下文体积并减少无效负载。"""
        subset = list(messages or [])[-max(1, int(max_items))]
        total = 0
        compacted: List[Dict[str, Any]] = []
        for item in reversed(subset):
            text = str(item.get("message") or item.get("content") or "")
            if not text:
                compacted.append(item)
                continue
            total += len(text)
            if total > max_chars:
                continue
            compacted.append(item)
        compacted.reverse()
        return compacted

    @staticmethod
    def compact_context(context: Dict[str, Any], *, max_len: int = 3200) -> Dict[str, Any]:
        """执行压缩上下文，控制上下文体积并减少无效负载。"""
        result: Dict[str, Any] = {}
        for key, value in (context or {}).items():
            if isinstance(value, str):
                result[key] = value[:max_len]
            elif isinstance(value, list):
                result[key] = value[:16]
            elif isinstance(value, dict):
                result[key] = {k: v for k, v in list(value.items())[:24]}
            else:
                result[key] = value
        return result
