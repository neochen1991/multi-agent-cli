from app.config import settings
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.messages import AgentEvidence


def _card(agent_name: str, phase: str, confidence: float = 0.6, **raw_output) -> AgentEvidence:
    return AgentEvidence(
        agent_name=agent_name,
        phase=phase,
        summary=f"{agent_name} summary",
        conclusion=raw_output.get("conclusion", f"{agent_name} conclusion"),
        evidence_chain=[],
        confidence=confidence,
        raw_output=dict(raw_output),
    )


def test_route_guardrail_forces_judge_after_critique_cycle_when_parallel_requested(monkeypatch):
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", True)

    round_cards = [
        _card("ProblemAnalysisAgent", "analysis", 0.45, open_questions=["需要更多证据"]),
        _card("LogAgent", "analysis", 0.65),
        _card("DomainAgent", "analysis", 0.95),
        _card("CodeAgent", "analysis", 0.72),
        _card("ProblemAnalysisAgent", "analysis", 0.55, missing_info=["日志样本不足"]),
        _card("CriticAgent", "critique", 0.45),
        _card("ProblemAnalysisAgent", "analysis", 0.40, open_questions=["仍需交叉验证"]),
        _card("RebuttalAgent", "rebuttal", 0.40),
        _card("ProblemAnalysisAgent", "analysis", 0.40, open_questions=["再补一轮并行证据"]),
    ]
    state = {
        "discussion_step_count": 9,
        "max_discussion_steps": 12,
    }
    route_decision = {
        "next_step": "analysis_parallel",
        "should_stop": False,
        "stop_reason": "",
        "reason": "主Agent请求再次并行分析",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False
    assert "批判/反驳链已完成" in str(guarded["reason"])


def test_route_guardrail_uses_agent_outputs_when_round_cards_missing(monkeypatch):
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", True)

    # No ProblemAnalysisAgent/JudgeAgent cards in round_cards, only analyst cards.
    round_cards = [
        _card("LogAgent", "analysis", 0.65),
        _card("DomainAgent", "analysis", 0.72),
        _card("CodeAgent", "analysis", 0.70),
        _card("CriticAgent", "critique", 0.44),
        _card("RebuttalAgent", "rebuttal", 0.43),
    ]
    state = {
        "discussion_step_count": 9,
        "max_discussion_steps": 12,
        "agent_outputs": {
            "ProblemAnalysisAgent": {
                "confidence": 0.83,
                "open_questions": [],
                "missing_info": [],
            },
            "JudgeAgent": {"confidence": 0.20},
            "LogAgent": {"confidence": 0.65},
            "DomainAgent": {"confidence": 0.72},
            "CodeAgent": {"confidence": 0.70},
            "CriticAgent": {"confidence": 0.44},
            "RebuttalAgent": {"confidence": 0.43},
        },
    }
    route_decision = {
        "next_step": "analysis_parallel",
        "should_stop": False,
        "stop_reason": "",
        "reason": "主Agent请求再次并行分析",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False


def test_fallback_route_uses_agent_outputs_when_round_cards_empty(monkeypatch):
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    decision = orchestrator._fallback_supervisor_route(
        state={
            "discussion_step_count": 3,
            "max_discussion_steps": 12,
            "agent_outputs": {
                "LogAgent": {"confidence": 0.66},
                "DomainAgent": {"confidence": 0.72},
                "CodeAgent": {"confidence": 0.70},
            },
        },
        round_cards=[],
    )

    assert decision["next_step"] == "speak:JudgeAgent"
    assert decision["should_stop"] is False
