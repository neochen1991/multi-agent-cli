"""Tests for langgraph routing strategy module."""

import pytest

from app.runtime.langgraph.routing_strategy import HybridRouter
from app.runtime.messages import AgentEvidence


def _card(agent_name: str, confidence: float = 0.6) -> AgentEvidence:
    return AgentEvidence(
        agent_name=agent_name,
        phase="analysis",
        summary="s",
        conclusion="c",
        evidence_chain=[],
        confidence=confidence,
        raw_output={},
    )


class _FakeOrchestrator:
    consensus_threshold = 0.75
    PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent", "MetricsAgent", "ChangeAgent", "RunbookAgent")

    def _route_guardrail(self, *, state, round_cards, route_decision):
        _ = state, round_cards
        return route_decision

    def _fallback_supervisor_route(self, state, round_cards):
        _ = state, round_cards
        return {"next_step": "speak:JudgeAgent", "should_stop": False, "stop_reason": "", "reason": "fallback"}

    async def _run_problem_analysis_supervisor_router(self, **kwargs):
        _ = kwargs
        return {"next_mode": "single", "next_agent": "LogAgent", "should_stop": False, "stop_reason": "", "commands": {}}

    def _route_from_commander_output(self, *, payload, state, round_cards):
        _ = payload, state, round_cards
        return {"next_step": "speak:LogAgent", "should_stop": False, "stop_reason": "", "reason": "dynamic"}

    def _recent_judge_card(self, round_cards):
        for card in reversed(round_cards):
            if card.agent_name == "JudgeAgent":
                return card
        return None

    def _compact_round_context(self, context):
        return context

    def _round_agent_counts(self, round_cards):
        counts = {}
        for card in round_cards:
            name = str(getattr(card, "agent_name", "") or "").strip()
            if not name:
                continue
            counts[name] = counts.get(name, 0) + 1
        return counts


@pytest.mark.asyncio
async def test_hybrid_router_seeded_path():
    router = HybridRouter()
    orch = _FakeOrchestrator()
    result = await router.decide(
        orchestrator=orch,
        state={},
        history_cards=[],
        round_cards=[],
        dialogue_items=[],
        loop_round=1,
        discussion_step_count=0,
        max_discussion_steps=12,
        preseed_step="speak:CodeAgent",
        supervisor_stop_requested=False,
        supervisor_stop_reason="",
    )
    assert result.mode == "langgraph_supervisor_seeded"
    assert result.decision["next_step"] == "speak:CodeAgent"


@pytest.mark.asyncio
async def test_hybrid_router_consensus_shortcut():
    router = HybridRouter()
    orch = _FakeOrchestrator()
    result = await router.decide(
        orchestrator=orch,
        state={},
        history_cards=[],
        round_cards=[_card("JudgeAgent", confidence=0.9)],
        dialogue_items=[],
        loop_round=1,
        discussion_step_count=2,
        max_discussion_steps=12,
        preseed_step="",
        supervisor_stop_requested=False,
        supervisor_stop_reason="",
    )
    assert result.mode == "langgraph_supervisor_consensus_shortcut"
    assert result.decision["should_stop"] is True


@pytest.mark.asyncio
async def test_hybrid_router_converges_to_judge_after_critique_cycle():
    router = HybridRouter()
    orch = _FakeOrchestrator()
    round_cards = [
        _card("LogAgent"),
        _card("DomainAgent"),
        _card("CodeAgent"),
        _card("MetricsAgent"),
        _card("ChangeAgent"),
        _card("RunbookAgent"),
        _card("CriticAgent"),
        _card("RebuttalAgent"),
    ]
    result = await router.decide(
        orchestrator=orch,
        state={},
        history_cards=list(round_cards),
        round_cards=round_cards,
        dialogue_items=[],
        loop_round=1,
        discussion_step_count=8,
        max_discussion_steps=12,
        preseed_step="",
        supervisor_stop_requested=False,
        supervisor_stop_reason="",
    )
    assert result.mode == "langgraph_supervisor_post_critique_converge"
    assert result.decision["next_step"] == "speak:JudgeAgent"
