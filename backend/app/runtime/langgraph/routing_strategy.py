"""Unified routing strategy interfaces for LangGraph runtime.

This module provides routing strategy implementations that use the new
rule-based engine for decision making.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

import structlog

from app.runtime.messages import AgentEvidence

logger = structlog.get_logger()


@dataclass
class StrategyResult:
    """Result from a routing strategy decision."""
    decision: Dict[str, Any]
    mode: str


class RoutingStrategy(Protocol):
    """Protocol for routing strategy implementations."""

    async def decide(
        self,
        *,
        orchestrator: Any,
        state: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_cards: List[AgentEvidence],
        dialogue_items: List[Dict[str, Any]],
        loop_round: int,
        discussion_step_count: int,
        max_discussion_steps: int,
        preseed_step: str,
        supervisor_stop_requested: bool,
        supervisor_stop_reason: str,
    ) -> StrategyResult:
        ...


class RuleBasedRouter:
    """Router that uses the rule engine for decisions.

    This router evaluates routing rules in priority order and returns
    the first matching decision. It serves as a fallback when LLM-based
    routing is unavailable or when the discussion reaches budget limits.
    """

    def __init__(self, rule_engine: Optional[Any] = None) -> None:
        """Initialize the rule-based router.

        Args:
            rule_engine: Optional RoutingRuleEngine instance.
                        If None, a default engine will be created lazily.
        """
        self._rule_engine = rule_engine

    def _get_rule_engine(self) -> Any:
        """Get or create the rule engine."""
        if self._rule_engine is None:
            from app.runtime.langgraph.routing.rule_engine import RoutingRuleEngine
            self._rule_engine = RoutingRuleEngine()
        return self._rule_engine

    async def decide(
        self,
        *,
        orchestrator: Any,
        state: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_cards: List[AgentEvidence],
        dialogue_items: List[Dict[str, Any]],
        loop_round: int,
        discussion_step_count: int,
        max_discussion_steps: int,
        preseed_step: str,
        supervisor_stop_requested: bool,
        supervisor_stop_reason: str,
    ) -> StrategyResult:
        """Make a routing decision using the rule engine."""
        _ = history_cards, dialogue_items, loop_round, preseed_step, supervisor_stop_requested, supervisor_stop_reason

        # Use fallback supervisor route for initial decision
        decision = orchestrator._fallback_supervisor_route(state=state, round_cards=round_cards)

        # Apply rule engine guardrails
        decision = orchestrator._route_guardrail(
            state=state,
            round_cards=round_cards,
            route_decision=decision,
        )

        return StrategyResult(decision=decision, mode="langgraph_supervisor_rule_based")


class DynamicLLMRouter:
    """Router that uses LLM for dynamic routing decisions.

    This router queries the ProblemAnalysisAgent (Commander) for
    routing decisions and applies guardrails afterwards.
    """

    async def decide(
        self,
        *,
        orchestrator: Any,
        state: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_cards: List[AgentEvidence],
        dialogue_items: List[Dict[str, Any]],
        loop_round: int,
        discussion_step_count: int,
        max_discussion_steps: int,
        preseed_step: str,
        supervisor_stop_requested: bool,
        supervisor_stop_reason: str,
    ) -> StrategyResult:
        """Make a routing decision using LLM-based dynamic routing."""
        _ = preseed_step, supervisor_stop_requested, supervisor_stop_reason

        context_summary = state.get("context_summary") or {}
        compact_context = orchestrator._compact_round_context(context_summary)

        commander_output = await orchestrator._run_problem_analysis_supervisor_router(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            round_history_cards=round_cards,
            dialogue_items=dialogue_items,
            discussion_step_count=discussion_step_count,
            max_discussion_steps=max_discussion_steps,
            existing_agent_outputs=dict(state.get("agent_outputs") or {}),
        )

        decision = orchestrator._route_from_commander_output(
            payload=commander_output,
            state=state,
            round_cards=round_cards,
        )

        # Commands are step-scoped; do not merge historical commands to avoid
        # stale command replay loops on weaker/unstable model outputs.
        decision["agent_commands"] = dict(commander_output.get("commands") or {})

        # Apply rule engine guardrails
        decision = orchestrator._route_guardrail(
            state=state,
            round_cards=round_cards,
            route_decision=decision,
        )

        return StrategyResult(decision=decision, mode="langgraph_supervisor_dynamic")


class HybridRouter:
    """Hybrid router with seeded/consensus/budget guard + dynamic LLM.

    This router implements a multi-stage decision process:
    1. Use preseed step for first step of discussion
    2. Check for consensus (high-confidence judge decision)
    3. Check budget limits
    4. Fall back to LLM-based dynamic routing
    5. Use rule-based routing as final fallback
    """

    def __init__(self, rule_engine: Optional[Any] = None) -> None:
        """Initialize the hybrid router.

        Args:
            rule_engine: Optional RoutingRuleEngine instance.
        """
        self._rule = RuleBasedRouter(rule_engine)
        self._dynamic = DynamicLLMRouter()
        self._rule_engine = rule_engine

    def _get_rule_engine(self) -> Any:
        """Get or create the rule engine."""
        if self._rule_engine is None:
            from app.runtime.langgraph.routing.rule_engine import RoutingRuleEngine
            self._rule_engine = RoutingRuleEngine()
        return self._rule_engine

    async def decide(
        self,
        *,
        orchestrator: Any,
        state: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_cards: List[AgentEvidence],
        dialogue_items: List[Dict[str, Any]],
        loop_round: int,
        discussion_step_count: int,
        max_discussion_steps: int,
        preseed_step: str,
        supervisor_stop_requested: bool,
        supervisor_stop_reason: str,
    ) -> StrategyResult:
        """Make a routing decision using the hybrid strategy."""
        # Stage 1: Use preseed step for first step
        if preseed_step and discussion_step_count == 0:
            decision = orchestrator._route_guardrail(
                state=state,
                round_cards=round_cards,
                route_decision={
                    "next_step": preseed_step,
                    "should_stop": supervisor_stop_requested,
                    "stop_reason": supervisor_stop_reason,
                    "reason": "采用主Agent开场拆解后的预置调度",
                },
            )
            return StrategyResult(
                decision=decision,
                mode="langgraph_supervisor_seeded",
            )

        # Stage 2: Check for consensus
        recent_judge_card = orchestrator._recent_judge_card(round_cards)
        recent_judge_conf = float(recent_judge_card.confidence or 0.0) if recent_judge_card else 0.0
        if recent_judge_card and recent_judge_conf >= orchestrator.consensus_threshold:
            decision = orchestrator._route_guardrail(
                state=state,
                round_cards=round_cards,
                route_decision={
                    "next_step": "",
                    "should_stop": True,
                    "stop_reason": "JudgeAgent 已给出高置信裁决",
                    "reason": "达到裁决阈值，主Agent结束讨论",
                },
            )
            return StrategyResult(
                decision=decision,
                mode="langgraph_supervisor_consensus_shortcut",
            )

        # Stage 3: Check budget limits
        if discussion_step_count >= max_discussion_steps:
            rb = await self._rule.decide(
                orchestrator=orchestrator,
                state=state,
                history_cards=history_cards,
                round_cards=round_cards,
                dialogue_items=dialogue_items,
                loop_round=loop_round,
                discussion_step_count=discussion_step_count,
                max_discussion_steps=max_discussion_steps,
                preseed_step=preseed_step,
                supervisor_stop_requested=supervisor_stop_requested,
                supervisor_stop_reason=supervisor_stop_reason,
            )
            rb.decision["reason"] = f"达到讨论步数预算({max_discussion_steps})，使用回退调度"
            rb.mode = "langgraph_supervisor_budget_guard"
            return rb

        # Stage 4: Try LLM-based dynamic routing
        try:
            return await self._dynamic.decide(
                orchestrator=orchestrator,
                state=state,
                history_cards=history_cards,
                round_cards=round_cards,
                dialogue_items=dialogue_items,
                loop_round=loop_round,
                discussion_step_count=discussion_step_count,
                max_discussion_steps=max_discussion_steps,
                preseed_step=preseed_step,
                supervisor_stop_requested=supervisor_stop_requested,
                supervisor_stop_reason=supervisor_stop_reason,
            )
        except Exception as e:
            logger.warning(
                "dynamic_routing_failed",
                error=str(e),
                session_id=getattr(orchestrator, "session_id", None),
            )
            # Stage 5: Fall back to rule-based routing
            rb = await self._rule.decide(
                orchestrator=orchestrator,
                state=state,
                history_cards=history_cards,
                round_cards=round_cards,
                dialogue_items=dialogue_items,
                loop_round=loop_round,
                discussion_step_count=discussion_step_count,
                max_discussion_steps=max_discussion_steps,
                preseed_step=preseed_step,
                supervisor_stop_requested=supervisor_stop_requested,
                supervisor_stop_reason=supervisor_stop_reason,
            )
            rb.mode = "langgraph_supervisor_fallback"
            return rb


__all__ = [
    "RoutingStrategy",
    "StrategyResult",
    "RuleBasedRouter",
    "DynamicLLMRouter",
    "HybridRouter",
]
