"""Centralized prompt composition for LangGraph runtime."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.runtime.langgraph.context_builders import (
    collect_peer_items_from_cards,
    collect_peer_items_from_dialogue,
    coordination_peer_items,
    history_items_for_agent_prompt,
    peer_items_for_collaboration_prompt,
    supervisor_recent_messages,
)
from app.runtime.langgraph.prompts import (
    build_agent_prompt,
    build_collaboration_prompt,
    build_peer_driven_prompt,
    build_problem_analysis_commander_prompt,
    build_problem_analysis_supervisor_prompt,
)
from app.runtime.langgraph.state import AgentSpec
from app.runtime.messages import AgentEvidence


class PromptBuilder:
    """Compose all runtime prompts from shared helper inputs."""

    def __init__(
        self,
        *,
        max_rounds: int,
        max_history_items: int,
        to_json: Callable[[Any], str],
        derive_conversation_state_with_context: Callable[..., Dict[str, Any]],
    ) -> None:
        self._max_rounds = int(max_rounds or 1)
        self._max_history_items = int(max_history_items or 2)
        self._to_json = to_json
        self._derive_conversation_state_with_context = derive_conversation_state_with_context

    def build_commander_prompt(
        self,
        *,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        peer_items = coordination_peer_items(
            history_cards=history_cards,
            dialogue_items=dialogue_items or [],
            existing_agent_outputs=existing_agent_outputs or {},
            limit=8,
        )
        return build_problem_analysis_commander_prompt(
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context,
            history_cards=history_cards,
            peer_items=peer_items,
            dialogue_items=dialogue_items,
            to_json=self._to_json,
        )

    def build_supervisor_prompt(
        self,
        *,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_history_cards: List[AgentEvidence],
        discussion_step_count: int,
        max_discussion_steps: int,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        convo_state = self._derive_conversation_state_with_context(
            history_cards,
            messages=[],
            existing_agent_outputs=existing_agent_outputs or {},
        )
        return build_problem_analysis_supervisor_prompt(
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context,
            round_history_cards=round_history_cards,
            recent_messages=supervisor_recent_messages(
                round_history_cards=round_history_cards,
                dialogue_items=dialogue_items or [],
                limit=10,
            ),
            open_questions=convo_state.get("open_questions") or [],
            dialogue_items=dialogue_items,
            discussion_step_count=discussion_step_count,
            max_discussion_steps=max_discussion_steps,
            to_json=self._to_json,
        )

    def build_peer_driven_prompt(
        self,
        *,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        peer_items = collect_peer_items_from_dialogue(
            dialogue_items or [],
            exclude_agent=spec.name,
            limit=max(2, self._max_history_items + 1),
        )
        if len(peer_items) < 2:
            fallback_peers = collect_peer_items_from_cards(
                history_cards,
                exclude_agent=spec.name,
                limit=max(2, self._max_history_items + 1),
            )
            known = {(str(i.get("agent") or ""), str(i.get("conclusion") or "")) for i in peer_items}
            for item in fallback_peers:
                sig = (str(item.get("agent") or ""), str(item.get("conclusion") or ""))
                if sig in known:
                    continue
                peer_items.append(item)
                known.add(sig)
                if len(peer_items) >= max(2, self._max_history_items + 1):
                    break
        return build_peer_driven_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context,
            peer_items=peer_items,
            assigned_command=assigned_command,
            dialogue_items=dialogue_items,
            inbox_items=inbox_messages,
            to_json=self._to_json,
        )

    def build_agent_prompt(
        self,
        *,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        return build_agent_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            max_history_items=self._max_history_items,
            context=context,
            history_cards=history_cards,
            history_items=history_items_for_agent_prompt(
                agent_name=spec.name,
                history_cards=history_cards,
                dialogue_items=dialogue_items or [],
                limit=max(1, self._max_history_items),
            ),
            assigned_command=assigned_command,
            dialogue_items=dialogue_items,
            inbox_items=inbox_messages,
            to_json=self._to_json,
        )

    def build_collaboration_prompt(
        self,
        *,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        peer_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        return build_collaboration_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context,
            peer_cards=peer_cards,
            peer_items=peer_items_for_collaboration_prompt(
                spec_name=spec.name,
                peer_cards=peer_cards,
                dialogue_items=dialogue_items or [],
                limit=max(2, len(peer_cards) if peer_cards else 2),
            ),
            assigned_command=assigned_command,
            dialogue_items=dialogue_items,
            inbox_items=inbox_messages,
            to_json=self._to_json,
        )


__all__ = ["PromptBuilder"]
