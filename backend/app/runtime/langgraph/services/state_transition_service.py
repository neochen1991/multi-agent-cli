"""State transition service for LangGraph runtime.

Encapsulates step-result merging and state projection so orchestrator remains
focused on lifecycle and wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.runtime.langgraph.state import (
    flatten_structured_overrides,
    flatten_structured_state_view,
)
from app.runtime.messages import AgentEvidence


@dataclass
class StateTransitionService:
    """Apply node step results onto debate state with message-first projection."""

    dedupe_new_messages: Callable[[List[Any], List[Any]], List[Any]]
    message_deltas_from_cards: Callable[[List[AgentEvidence]], List[Any]]
    derive_conversation_state: Callable[..., Dict[str, Any]]
    messages_to_cards: Callable[[List[Any]], List[AgentEvidence]]
    merge_round_and_message_cards: Callable[[List[AgentEvidence], List[AgentEvidence]], List[AgentEvidence]]
    structured_snapshot: Callable[[Dict[str, Any]], Dict[str, Any]]

    def apply_step_result(
        self,
        state: Dict[str, Any],
        result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        base_state = flatten_structured_state_view(state or {})
        result_payload = dict(result or {})
        result_overrides = flatten_structured_overrides(result_payload)

        current_messages = list(state.get("messages") or [])
        prev_history_cards = list(base_state.get("history_cards") or [])
        has_history_update = "history_cards" in result_overrides
        next_history_cards = (
            list(result_overrides.get("history_cards") or [])
            if has_history_update
            else prev_history_cards
        )
        new_cards = next_history_cards[len(prev_history_cards):]

        explicit_messages = list(result_payload.get("messages") or [])
        derived_messages = self.message_deltas_from_cards(new_cards) if not explicit_messages else []
        new_messages = explicit_messages or derived_messages
        deduped_messages = self.dedupe_new_messages(current_messages, new_messages)
        merged_messages = current_messages + list(deduped_messages or [])

        # message-first projection: history cards are a projection from round cards + messages.
        message_cards = self.messages_to_cards(merged_messages)
        projected_history_cards = self.merge_round_and_message_cards(next_history_cards, message_cards)

        step_delta = len(new_cards)
        if step_delta <= 0 and deduped_messages:
            # keep progress moving if a node only emitted messages.
            step_delta = 1

        convo_state = self.derive_conversation_state(
            projected_history_cards,
            messages=merged_messages,
            existing_agent_outputs=dict(base_state.get("agent_outputs") or {}),
        )

        next_state = {
            **result_payload,
            **result_overrides,
            "next_step": "",
            "history_cards": projected_history_cards,
            "discussion_step_count": int(base_state.get("discussion_step_count") or 0) + step_delta,
            **({"messages": deduped_messages} if deduped_messages else {}),
            **convo_state,
        }
        merged_preview = {**dict(state), **next_state}
        return {**next_state, **self.structured_snapshot(merged_preview)}
