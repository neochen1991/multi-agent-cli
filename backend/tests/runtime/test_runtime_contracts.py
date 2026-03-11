"""Runtime contract tests that freeze compatibility during refactors."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.runtime.langgraph.state import DebateTurn, build_session_init_update, structured_state_snapshot
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.messages import AgentEvidence


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


def test_build_session_init_update_keeps_canonical_runtime_shape():
    payload = build_session_init_update(max_discussion_steps=9)

    assert payload["messages"] == []
    assert payload["history_cards"] == []
    assert payload["agent_outputs"] == {}
    assert payload["agent_commands"] == {}
    assert payload["agent_mailbox"] == {}
    assert payload["max_discussion_steps"] == 9
    assert payload["phase_state"]["current_round"] == 0
    assert payload["routing_state"]["discussion_step_count"] == 0
    assert payload["output_state"]["open_questions"] == []


def test_structured_state_snapshot_preserves_flat_state_projection():
    state = {
        "current_round": 2,
        "executed_rounds": 1,
        "consensus_reached": True,
        "continue_next_round": False,
        "next_step": "judge_agent_node",
        "agent_commands": {"LogAgent": {"task": "检查首错"}},
        "discussion_step_count": 3,
        "max_discussion_steps": 12,
        "round_start_turn_index": 5,
        "agent_mailbox": {"JudgeAgent": [{"message_type": "feedback"}]},
        "supervisor_stop_requested": False,
        "supervisor_stop_reason": "",
        "supervisor_notes": [{"next_step": "judge_agent_node"}],
        "awaiting_human_review": False,
        "human_review_reason": "",
        "human_review_payload": {},
        "resume_from_step": "",
        "history_cards": [],
        "agent_outputs": {"LogAgent": {"confidence": 0.7}},
        "evidence_chain": [{"type": "log"}],
        "claims": [{"agent_name": "LogAgent"}],
        "open_questions": ["数据库锁等待是否先发生"],
        "final_payload": {"summary": "初步确认数据库争用"},
    }

    snapshot = structured_state_snapshot(state)

    assert snapshot["phase_state"]["current_round"] == 2
    assert snapshot["phase_state"]["consensus_reached"] is True
    assert snapshot["routing_state"]["next_step"] == "judge_agent_node"
    assert snapshot["routing_state"]["agent_commands"]["LogAgent"]["task"] == "检查首错"
    assert snapshot["routing_state"]["agent_mailbox"]["JudgeAgent"][0]["message_type"] == "feedback"
    assert snapshot["output_state"]["agent_outputs"]["LogAgent"]["confidence"] == 0.7
    assert snapshot["output_state"]["open_questions"] == ["数据库锁等待是否先发生"]
    assert snapshot["output_state"]["final_payload"]["summary"] == "初步确认数据库争用"


def test_structured_state_snapshot_preserves_richer_checkpoint_fields():
    """结构化快照应保留恢复所需的 richer state。"""

    state = {
        "current_round": 3,
        "continue_next_round": True,
        "resume_from_step": "report_generation",
        "agent_local_state": {
            "CodeAgent": {
                "latest_conclusion": "事务边界过长",
                "missing_checks": ["核对连接释放路径"],
            }
        },
        "top_k_hypotheses": [{"agent_name": "CodeAgent", "conclusion": "事务边界过长", "confidence": 0.82}],
        "evidence_coverage": {
            "ok": 2,
            "degraded": 0,
            "missing": 0,
            "corroboration_count": 1,
            "weighted_score": 0.88,
        },
        "round_gap_summary": ["Top-2 根因候选尚未收敛，需要继续交叉验证。"],
        "round_objectives": ["优先验证 Top-1 候选：事务边界过长"],
        "debate_stability_score": 0.74,
    }

    snapshot = structured_state_snapshot(state)

    assert snapshot["routing_state"]["resume_from_step"] == "report_generation"
    assert snapshot["output_state"]["agent_local_state"]["CodeAgent"]["latest_conclusion"] == "事务边界过长"
    assert snapshot["output_state"]["evidence_coverage"]["corroboration_count"] == 1
    assert snapshot["routing_state"]["round_gap_summary"] == ["Top-2 根因候选尚未收敛，需要继续交叉验证。"]
    assert snapshot["routing_state"]["round_objectives"] == ["优先验证 Top-1 候选：事务边界过长"]


def test_history_cards_for_state_prefers_round_slice_and_message_fallback():
    orchestrator = _orchestrator()
    cards = [
        AgentEvidence(
            agent_name="ProblemAnalysisAgent",
            phase="coordination",
            summary="主控拆解",
            conclusion="派发日志与代码调查",
            evidence_chain=[],
            confidence=0.55,
            raw_output={},
        ),
        AgentEvidence(
            agent_name="LogAgent",
            phase="analysis",
            summary="日志时间线",
            conclusion="HikariPool 先超时，随后出现 502",
            evidence_chain=[],
            confidence=0.71,
            raw_output={},
        ),
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码闭包",
            conclusion="事务持锁过长",
            evidence_chain=[],
            confidence=0.66,
            raw_output={},
        ),
    ]
    state = {
        "history_cards": cards,
        "round_start_turn_index": 1,
        "messages": [],
    }

    round_cards = orchestrator._round_cards_for_routing(state)

    assert [item.agent_name for item in round_cards] == ["LogAgent", "CodeAgent"]


@pytest.mark.asyncio
async def test_graph_round_start_aligns_round_slice_with_history_cards(monkeypatch):
    """round_start 的切片锚点必须和 history_cards 视图一致，不能被 commander turn 数量带偏。"""

    orchestrator = _orchestrator()

    async def _fake_emit_event(payload):
        _ = payload

    async def _fake_run_problem_analysis_commander(**kwargs):
        _ = kwargs
        orchestrator.turns.append(
            DebateTurn(
                round_number=1,
                phase="coordination",
                agent_name="ProblemAnalysisAgent",
                agent_role="主控",
                model={},
                input_message="拆解问题",
                output_content={"conclusion": "先让四个基础专家并行分析"},
                confidence=0.62,
                completed_at=datetime.utcnow(),
            )
        )
        return {
            "commands": {
                "LogAgent": {"task": "分析日志"},
                "DomainAgent": {"task": "分析领域"},
                "CodeAgent": {"task": "分析代码"},
                "DatabaseAgent": {"task": "分析数据库"},
            }
        }

    monkeypatch.setattr(orchestrator, "_emit_event", _fake_emit_event)
    monkeypatch.setattr(orchestrator, "_run_problem_analysis_commander", _fake_run_problem_analysis_commander)
    monkeypatch.setattr(
        orchestrator,
        "_route_from_commander_output",
        lambda payload, state, round_cards: {
            "next_step": "analysis_parallel",
            "should_stop": False,
            "stop_reason": "",
        },
    )

    next_state = await orchestrator._graph_round_start(
        {
            "current_round": 0,
            "history_cards": [],
            "messages": [],
            "agent_outputs": {},
            "agent_mailbox": {},
            "context_summary": {},
        }
    )

    assert next_state["round_start_turn_index"] == len(next_state["history_cards"]) == 0

    analysis_cards = [
        AgentEvidence(agent_name="LogAgent", phase="analysis", summary="日志", conclusion="日志结论", evidence_chain=[], confidence=0.71, raw_output={}),
        AgentEvidence(agent_name="DomainAgent", phase="analysis", summary="领域", conclusion="领域结论", evidence_chain=[], confidence=0.73, raw_output={}),
        AgentEvidence(agent_name="CodeAgent", phase="analysis", summary="代码", conclusion="代码结论", evidence_chain=[], confidence=0.81, raw_output={}),
        AgentEvidence(agent_name="DatabaseAgent", phase="analysis", summary="数据库", conclusion="数据库结论", evidence_chain=[], confidence=0.75, raw_output={}),
    ]
    round_cards = orchestrator._round_cards_for_routing(
        {
            **next_state,
            "history_cards": list(next_state["history_cards"]) + analysis_cards,
            "messages": [],
        }
    )

    assert [item.agent_name for item in round_cards] == [
        "LogAgent",
        "DomainAgent",
        "CodeAgent",
        "DatabaseAgent",
    ]
