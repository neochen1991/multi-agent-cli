"""Agent execution runner for LangGraph runtime."""

from __future__ import annotations

from typing import Any, Optional

from app.runtime.langgraph.execution import call_agent
from app.runtime.langgraph.state import AgentSpec, DebateTurn


class AgentRunner:
    """Single place for agent invocation + fallback policy."""

    def __init__(self, orchestrator: Any):
        self._orchestrator = orchestrator

    async def run_agent(
        self,
        *,
        spec: AgentSpec,
        prompt: str,
        round_number: int,
        loop_round: int,
        history_cards_context: Optional[list[Any]] = None,
    ) -> DebateTurn:
        try:
            return await call_agent(
                self._orchestrator,
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
                history_cards_context=history_cards_context,
            )
        except Exception as exc:  # pragma: no cover - fallback path
            error_text = str(exc).strip() or exc.__class__.__name__
            return await self._orchestrator._create_fallback_turn(
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
                error_text=error_text,
            )


__all__ = ["AgentRunner"]
