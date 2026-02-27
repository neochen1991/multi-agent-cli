"""Unified routing strategy interfaces for LangGraph runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

from app.runtime.messages import AgentEvidence


@dataclass
class StrategyResult:
    decision: Dict[str, Any]
    mode: str


class RoutingStrategy(Protocol):
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
        _ = history_cards, dialogue_items, loop_round, preseed_step, supervisor_stop_requested, supervisor_stop_reason
        decision = orchestrator._fallback_supervisor_route(state=state, round_cards=round_cards)
        decision = orchestrator._route_guardrail(
            state=state,
            round_cards=round_cards,
            route_decision=decision,
        )
        return StrategyResult(decision=decision, mode="langgraph_supervisor_rule_based")


class DynamicLLMRouter:
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
        merged_commands = dict(state.get("agent_commands") or {})
        merged_commands.update(dict(commander_output.get("commands") or {}))
        decision["agent_commands"] = merged_commands
        decision = orchestrator._route_guardrail(
            state=state,
            round_cards=round_cards,
            route_decision=decision,
        )
        return StrategyResult(decision=decision, mode="langgraph_supervisor_dynamic")


class HybridRouter:
    """Hybrid router with seeded/consensus/budget guard + dynamic LLM."""

    def __init__(self) -> None:
        self._rule = RuleBasedRouter()
        self._dynamic = DynamicLLMRouter()

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
        except Exception:
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
