"""Context service for LangGraph debate runtime.

This module provides context building and management functionality.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from app.runtime.messages import AgentEvidence

logger = structlog.get_logger()


class ContextService:
    """Context building and management.

    This service handles:
    - Context summarization
    - Peer item collection
    - Dialogue item extraction
    """

    def __init__(self) -> None:
        """Initialize the context service."""
        self._context_cache: Dict[str, Dict[str, Any]] = {}

    def compact_round_context(
        self,
        context_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a compact context for the round.

        Args:
            context_summary: The context summary.

        Returns:
            A compacted context dictionary.
        """
        if not context_summary:
            return {}

        # Extract key fields for compact context
        compact = {
            "incident_summary": context_summary.get("incident_summary", ""),
            "error_type": context_summary.get("error_type", ""),
            "key_entities": list(context_summary.get("key_entities", []))[:5],
            "time_range": context_summary.get("time_range", {}),
            "affected_services": list(context_summary.get("affected_services", []))[:3],
        }

        # Remove empty values
        return {k: v for k, v in compact.items() if v}

    def collect_peer_items_from_cards(
        self,
        history_cards: List[AgentEvidence],
        agent_names: List[str],
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Collect peer items from agent cards.

        Args:
            history_cards: List of agent evidence cards.
            agent_names: Names of agents to collect from.
            limit: Maximum items per agent.

        Returns:
            List of peer items.
        """
        peer_items = []
        seen_agents = set()

        for card in reversed(history_cards):
            if card.agent_name in agent_names and card.agent_name not in seen_agents:
                peer_items.append({
                    "agent_name": card.agent_name,
                    "conclusion": str(card.conclusion or "")[:500],
                    "confidence": float(card.confidence or 0.0),
                    "evidence_chain": list(card.evidence_chain or [])[:limit],
                })
                seen_agents.add(card.agent_name)

                if len(seen_agents) >= len(agent_names):
                    break

        return peer_items

    def dialogue_items_from_messages(
        self,
        messages: List[Any],
        limit: int = 6,
        char_budget: int = 720,
    ) -> List[Dict[str, Any]]:
        """Extract dialogue items from messages.

        Args:
            messages: List of messages.
            limit: Maximum number of items.
            char_budget: Character budget for content.

        Returns:
            List of dialogue items.
        """
        items = []
        total_chars = 0

        for msg in reversed(messages):
            if len(items) >= limit:
                break

            content = ""
            if hasattr(msg, "content"):
                content = str(msg.content or "")
            elif isinstance(msg, dict):
                content = str(msg.get("content", ""))

            if not content.strip():
                continue

            sender = "unknown"
            if hasattr(msg, "name") and msg.name:
                sender = str(msg.name)
            elif isinstance(msg, dict):
                sender = str(msg.get("name", "unknown"))

            # Truncate to budget
            if total_chars + len(content) > char_budget:
                remaining = char_budget - total_chars
                if remaining > 50:
                    content = content[:remaining] + "..."
                else:
                    break

            items.append({
                "sender": sender,
                "content": content,
            })
            total_chars += len(content)

        return list(reversed(items))

    def derive_conversation_state(
        self,
        history_cards: List[AgentEvidence],
        messages: List[Any],
        existing_agent_outputs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Derive conversation state from history.

        Args:
            history_cards: List of agent evidence cards.
            messages: List of messages.
            existing_agent_outputs: Existing agent outputs.

        Returns:
            Derived conversation state.
        """
        # Collect open questions
        open_questions = []
        for output in existing_agent_outputs.values():
            if isinstance(output, dict):
                for key in ("open_questions", "missing_info", "needs_validation"):
                    value = output.get(key)
                    if isinstance(value, list):
                        open_questions.extend([
                            str(v or "").strip() for v in value
                            if str(v or "").strip()
                        ])
                    elif isinstance(value, str) and value.strip():
                        open_questions.append(value.strip())

        # Dedupe while preserving order
        seen = set()
        unique_questions = []
        for q in open_questions:
            if q not in seen:
                seen.add(q)
                unique_questions.append(q)

        # Collect claims
        claims = []
        for card in history_cards:
            if card.conclusion:
                claims.append({
                    "agent_name": card.agent_name,
                    "claim": str(card.conclusion)[:200],
                    "confidence": float(card.confidence or 0.0),
                })

        return {
            "open_questions": unique_questions[:10],
            "claims": claims[-10:],
            "total_turns": len(history_cards),
            "unique_agents": len(set(c.agent_name for c in history_cards if c.agent_name)),
        }

    def build_agent_prompt_context(
        self,
        spec: Any,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build context for agent prompt.

        Args:
            spec: Agent specification.
            loop_round: Current loop round.
            context: Compact context.
            history_cards: History cards.
            assigned_command: Optional command for this agent.
            dialogue_items: Optional dialogue items.
            inbox_messages: Optional inbox messages.

        Returns:
            Context dictionary for prompt building.
        """
        return {
            "agent_name": spec.name,
            "agent_role": spec.role,
            "loop_round": loop_round,
            "context": context,
            "recent_history": [
                {
                    "agent_name": c.agent_name,
                    "conclusion": str(c.conclusion or "")[:300],
                    "confidence": float(c.confidence or 0.0),
                }
                for c in history_cards[-5:]
            ],
            "assigned_command": assigned_command,
            "dialogue_items": dialogue_items or [],
            "inbox_messages": inbox_messages or [],
        }

    def clear_cache(self) -> None:
        """Clear the context cache."""
        self._context_cache.clear()


__all__ = ["ContextService"]