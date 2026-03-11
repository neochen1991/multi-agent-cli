"""Pure state/message projection helpers for runtime orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.runtime.langgraph.message_ops import (
    merge_round_and_message_cards as merge_round_and_message_cards_ops,
    messages_to_cards as messages_to_cards_ops,
)
from app.runtime.messages import AgentEvidence


def round_cards_from_state(state: Dict[str, Any]) -> List[AgentEvidence]:
    """Slice current-round cards from stored history."""
    history_cards = list(state.get("history_cards") or [])
    start_index = max(0, int(state.get("round_start_turn_index") or 0))
    if start_index <= 0:
        return history_cards
    return history_cards[start_index:]


def messages_to_cards(messages: List[Any], *, limit: int = 12) -> List[AgentEvidence]:
    """Project LangGraph messages into evidence cards."""
    return messages_to_cards_ops(messages, limit=limit)


def history_cards_for_state(state: Dict[str, Any], *, limit: int = 20) -> List[AgentEvidence]:
    """Build display cards with stored history plus latest message projection."""
    stored_cards = list(state.get("history_cards") or [])
    message_cards = messages_to_cards(list(state.get("messages") or []), limit=max(8, limit))
    return merge_round_and_message_cards_ops(stored_cards, message_cards, limit=max(8, limit))


def round_cards_for_routing(state: Dict[str, Any]) -> List[AgentEvidence]:
    """Build current-round cards for routing, merged with recent message projection."""
    round_cards = round_cards_from_state(state)
    message_cards = messages_to_cards(list(state.get("messages") or []), limit=12)
    return merge_round_and_message_cards_ops(round_cards, message_cards, limit=20)


def dialogue_items_from_messages(
    messages: List[Any],
    *,
    limit: int = 8,
    char_budget: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Extract compact prompt-friendly dialogue items from message history."""
    budget = max(240, int(char_budget or 900))
    items: List[Dict[str, Any]] = []
    seen_signatures: set[tuple[str, str]] = set()
    used_chars = 0
    for msg in reversed(list(messages or [])):
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content_text = " ".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict)
            ).strip()
        else:
            content_text = str(content or "").strip()
        if not content_text:
            continue
        additional = getattr(msg, "additional_kwargs", {}) or {}
        speaker = (
            str(getattr(msg, "name", "") or "")
            or str(additional.get("agent_name") or "")
            or str(getattr(msg, "type", "") or "assistant")
        )
        sig = (speaker, content_text[:64])
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        msg_snippet = content_text[:140]
        conclusion_snippet = str(additional.get("conclusion") or "")[:96]
        estimated = len(msg_snippet) + len(conclusion_snippet) + len(speaker) + 24
        if items and used_chars + estimated > budget:
            continue
        used_chars += estimated
        items.append(
            {
                "speaker": speaker,
                "phase": str(additional.get("phase") or ""),
                "conclusion": conclusion_snippet,
                "message": msg_snippet,
            }
        )
        if len(items) >= max(1, limit):
            break
    items.reverse()
    return items
