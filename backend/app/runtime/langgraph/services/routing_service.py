"""Routing service for orchestration-level route decisions."""

from __future__ import annotations

from typing import Any, Dict

from app.runtime.langgraph.routing import (
    agent_from_step as agent_from_step_route,
    step_for_agent as step_for_agent_route,
    supervisor_step_to_node as supervisor_step_to_node_route,
)


class RoutingService:
    """Encapsulate route decision helpers used by orchestrator."""

    @staticmethod
    def route_after_analysis_parallel(*, enable_collaboration: bool) -> str:
        return "analysis_collaboration" if bool(enable_collaboration) else "critic"

    @staticmethod
    def route_after_critic(*, enable_critique: bool) -> str:
        return "rebuttal" if bool(enable_critique) else "judge"

    @staticmethod
    def supervisor_step_to_node(next_step: str) -> str:
        return supervisor_step_to_node_route(next_step)

    def route_after_supervisor_decide(self, state: Dict[str, Any]) -> str:
        return self.supervisor_step_to_node(str((state or {}).get("next_step") or ""))

    @staticmethod
    def route_after_round_evaluate(state: Dict[str, Any]) -> str:
        return "round_start" if bool((state or {}).get("continue_next_round")) else "finalize"

    @staticmethod
    def round_discussion_budget(
        *,
        base_steps: int,
        enable_collaboration: bool,
        enable_critique: bool,
    ) -> int:
        base = int(base_steps or 0)
        if bool(enable_collaboration):
            base += 2
        if not bool(enable_critique):
            base = max(4, base - 2)
        return max(4, min(base, 24))

    @staticmethod
    def step_for_agent(agent_name: str) -> str:
        return step_for_agent_route(agent_name)

    @staticmethod
    def agent_from_step(step: str) -> str:
        return agent_from_step_route(step)

