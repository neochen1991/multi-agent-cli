"""Message/state helper ops for LangGraph runtime."""

from __future__ import annotations

from typing import Any, List, Sequence

from app.runtime.messages import AgentEvidence


def message_signature(msg: Any) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        content_text = " ".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        ).strip()
    else:
        content_text = str(content or "").strip()
    additional = getattr(msg, "additional_kwargs", {}) or {}
    speaker = (
        str(getattr(msg, "name", "") or "")
        or str(additional.get("agent_name") or "")
        or str(getattr(msg, "type", "") or "assistant")
    )
    return f"{speaker}:{content_text[:180]}"


def dedupe_new_messages(existing_messages: Sequence[Any], new_messages: Sequence[Any]) -> List[Any]:
    if not new_messages:
        return []
    seen = {message_signature(msg) for msg in list(existing_messages or [])[-80:]}
    deduped: List[Any] = []
    for msg in list(new_messages or []):
        sig = message_signature(msg)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(msg)
    return deduped


def messages_to_cards(messages: Sequence[Any], *, limit: int = 12) -> List[AgentEvidence]:
    cards: List[AgentEvidence] = []
    for msg in list(messages or [])[-max(1, int(limit or 1)) :]:
        additional = getattr(msg, "additional_kwargs", {}) or {}
        agent_name = (
            str(getattr(msg, "name", "") or "")
            or str(additional.get("agent_name") or "")
        ).strip()
        if not agent_name:
            continue
        phase = str(additional.get("phase") or "").strip() or "analysis"
        conclusion = str(additional.get("conclusion") or "").strip()
        confidence_raw = additional.get("confidence")
        try:
            confidence = float(confidence_raw or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            summary = " ".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict)
            ).strip()
        else:
            summary = str(content or "").strip()
        if not summary and not conclusion:
            continue
        cards.append(
            AgentEvidence(
                agent_name=agent_name,
                phase=phase,
                summary=summary[:200],
                conclusion=(conclusion or summary)[:220],
                evidence_chain=[],
                confidence=max(0.0, min(confidence, 1.0)),
                raw_output={},
            )
        )
    return cards


def merge_round_and_message_cards(
    round_cards: Sequence[AgentEvidence],
    message_cards: Sequence[AgentEvidence],
    *,
    limit: int = 20,
) -> List[AgentEvidence]:
    base = list(round_cards or [])
    if not base:
        return list(message_cards or [])[-max(1, int(limit or 1)) :]
    if not message_cards:
        return base[-max(1, int(limit or 1)) :]
    seen = {
        (
            str(card.agent_name or "").strip(),
            str(card.conclusion or "").strip()[:120],
        )
        for card in base
    }
    merged = list(base)
    for card in list(message_cards or []):
        sig = (
            str(card.agent_name or "").strip(),
            str(card.conclusion or "").strip()[:120],
        )
        if sig in seen:
            continue
        seen.add(sig)
        merged.append(card)
    return merged[-max(1, int(limit or 1)) :]


__all__ = [
    "message_signature",
    "dedupe_new_messages",
    "messages_to_cards",
    "merge_round_and_message_cards",
]
