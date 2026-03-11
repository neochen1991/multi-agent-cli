"""Structured-state contract tests for critical runtime paths."""

from __future__ import annotations

import pytest

from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=4)


@pytest.mark.asyncio
async def test_graph_round_evaluate_prefers_structured_state_fields():
    orchestrator = _orchestrator()
    events: list[dict] = []

    async def _callback(payload: dict) -> None:
        events.append(dict(payload))

    orchestrator._event_callback = _callback
    state = {
        "current_round": 1,
        "executed_rounds": 0,
        "supervisor_stop_requested": False,
        "history_cards": [],
        "phase_state": {
            "current_round": 3,
            "executed_rounds": 2,
            "consensus_reached": False,
            "continue_next_round": True,
            "debate_stability_score": 0.0,
        },
        "routing_state": {
            "supervisor_stop_requested": True,
            "supervisor_stop_reason": "manual stop from nested state",
            "next_step": "speak:JudgeAgent",
        },
        "output_state": {
            "history_cards": [],
            "agent_outputs": {},
            "evidence_chain": [],
            "claims": [],
            "open_questions": [],
            "final_payload": {},
            "top_k_hypotheses": [{"agent_name": "LogAgent", "conclusion": "db lock"}],
            "evidence_coverage": {"ok": 1, "degraded": 0, "missing": 0},
        },
    }

    result = await orchestrator._graph_round_evaluate(state)

    assert result["executed_rounds"] == 3
    assert result["continue_next_round"] is False
    assert result["top_k_hypotheses"] == [{"agent_name": "LogAgent", "conclusion": "db lock"}]
    assert events[-1]["loop_round"] == 3
    assert events[-1]["supervisor_stop_requested"] is True
