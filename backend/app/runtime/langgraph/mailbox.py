"""Explicit inter-agent mailbox helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.runtime.messages import AgentMessage


def clone_mailbox(mailbox: Dict[str, List[Dict[str, Any]]] | None) -> Dict[str, List[Dict[str, Any]]]:
    source = dict(mailbox or {})
    return {str(k): [dict(item) for item in list(v or [])] for k, v in source.items()}


def enqueue_message(
    mailbox: Dict[str, List[Dict[str, Any]]],
    *,
    receiver: str,
    message: AgentMessage,
    max_per_receiver: int = 20,
) -> None:
    key = str(receiver or "").strip()
    if not key:
        return
    bucket = list(mailbox.get(key) or [])
    bucket.append(message.model_dump(mode="json"))
    if len(bucket) > max_per_receiver:
        bucket = bucket[-max_per_receiver:]
    mailbox[key] = bucket


def dequeue_messages(
    mailbox: Dict[str, List[Dict[str, Any]]],
    *,
    receiver: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    copied = clone_mailbox(mailbox)
    key = str(receiver or "").strip()
    items = list(copied.pop(key, []) or [])
    return items, copied


def compact_mailbox(mailbox: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    compacted: Dict[str, List[Dict[str, Any]]] = {}
    for receiver, messages in (mailbox or {}).items():
        arr = [dict(item) for item in list(messages or []) if isinstance(item, dict)]
        if arr:
            compacted[str(receiver)] = arr[-20:]
    return compacted


__all__ = [
    "clone_mailbox",
    "enqueue_message",
    "dequeue_messages",
    "compact_mailbox",
]

