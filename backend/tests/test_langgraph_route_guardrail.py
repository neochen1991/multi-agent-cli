"""testlanggraph路由guardrail相关测试。"""

from app.config import settings
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.messages import AgentEvidence


def _card(agent_name: str, phase: str, confidence: float = 0.6, **raw_output) -> AgentEvidence:
    """为测试场景提供卡片辅助逻辑。"""
    
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
    """验证路由guardrailforces裁决后critiquecycle当并行requested。"""
    
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


def test_route_guardrail_uses_agent_outputs_when_round_cards_missing(monkeypatch):
    """验证路由guardrail使用Agentoutputs当轮次cards缺失。"""
    
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
    """验证回退路由使用Agentoutputs当轮次cards空。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    decision = orchestrator._fallback_supervisor_route(
        state={
            "discussion_step_count": 3,
            "max_discussion_steps": 12,
            "agent_outputs": {
                "LogAgent": {"confidence": 0.66, "conclusion": "日志显示连接池获取超时"},
                "DomainAgent": {"confidence": 0.72},
                "CodeAgent": {"confidence": 0.70, "conclusion": "代码路径存在连接释放延迟"},
                "DatabaseAgent": {"confidence": 0.68, "conclusion": "数据库连接获取超时与锁等待并发出现"},
                "MetricsAgent": {"confidence": 0.63, "conclusion": "数据库等待时间与接口延迟同时升高"},
            },
        },
        round_cards=[],
    )

    assert decision["next_step"] == "analysis_parallel"
    assert decision["should_stop"] is False


def test_commander_route_stops_after_effective_judge_when_next_agent_only_retries_degraded_evidence(monkeypatch):
    """验证主Agent路由stops后有效裁决当nextAgentonlyretries降级证据。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    round_cards = [
        _card(
            "JudgeAgent",
            "judgment",
            0.46,
            final_judgment={
                "root_cause": {
                    "summary": "数据库连接池(HikariPool)连接获取超时",
                    "confidence": 0.46,
                }
            },
            conclusion="数据库连接池(HikariPool)连接获取超时",
        ),
        _card(
            "ProblemAnalysisAgent",
            "judgment",
            0.42,
            conclusion="当前结论：数据库连接池(HikariPool)连接获取超时",
        ),
        _card(
            "DatabaseAgent",
            "analysis",
            0.18,
            conclusion="DatabaseAgent 调用超时，已降级继续",
            degraded=True,
            evidence_status="degraded",
            tool_status="timeout",
        ),
    ]

    decision = orchestrator._route_from_commander_output(
        payload={
            "next_mode": "single",
            "next_agent": "DatabaseAgent",
            "should_stop": False,
            "stop_reason": "",
        },
        state={
            "discussion_step_count": 9,
            "max_discussion_steps": 10,
            "agent_outputs": {
                "JudgeAgent": {
                    "final_judgment": {
                        "root_cause": {
                            "summary": "数据库连接池(HikariPool)连接获取超时",
                            "confidence": 0.46,
                        }
                    }
                },
                "ProblemAnalysisAgent": {
                    "conclusion": "当前结论：数据库连接池(HikariPool)连接获取超时",
                    "confidence": 0.42,
                },
                "DatabaseAgent": {
                    "conclusion": "DatabaseAgent 调用超时，已降级继续",
                    "degraded": True,
                    "evidence_status": "degraded",
                },
            },
        },
        round_cards=round_cards,
    )

    assert decision["should_stop"] is True
    assert decision["next_step"] == ""


def test_commander_route_keeps_collecting_when_judge_not_yet_actionable(monkeypatch):
    """验证主Agent路由保留collecting当裁决notyetactionable。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    round_cards = [
        _card(
            "JudgeAgent",
            "judgment",
            0.28,
            final_judgment={
                "root_cause": {
                    "summary": "仍需补充日志与代码证据",
                    "confidence": 0.28,
                }
            },
            conclusion="仍需补充日志与代码证据",
        ),
        _card(
            "ProblemAnalysisAgent",
            "analysis",
            0.34,
            open_questions=["日志样本不足", "代码入口未确认"],
        ),
    ]

    decision = orchestrator._route_from_commander_output(
        payload={
            "next_mode": "single",
            "next_agent": "LogAgent",
            "should_stop": False,
            "stop_reason": "",
        },
        state={
            "discussion_step_count": 4,
            "max_discussion_steps": 10,
            "agent_outputs": {
                "JudgeAgent": {
                    "final_judgment": {
                        "root_cause": {
                            "summary": "仍需补充日志与代码证据",
                            "confidence": 0.28,
                        }
                    }
                },
                "ProblemAnalysisAgent": {
                    "open_questions": ["日志样本不足", "代码入口未确认"],
                    "confidence": 0.34,
                },
            },
        },
        round_cards=round_cards,
    )

    assert decision["should_stop"] is False
    assert decision["next_step"] == "speak:LogAgent"


def test_commander_route_stops_after_effective_judge_when_commander_already_summarized(monkeypatch):
    """验证主Agent路由stops后有效裁决当主Agentalreadysummarized。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    round_cards = [
        _card(
            "JudgeAgent",
            "judgment",
            0.51,
            final_judgment={
                "root_cause": {
                    "summary": "订单定价链路中数据库连接池获取超时",
                    "confidence": 0.51,
                }
            },
            conclusion="订单定价链路中数据库连接池获取超时",
        ),
        _card(
            "ProblemAnalysisAgent",
            "judgment",
            0.48,
            conclusion="我已汇总各专家反馈，当前结论：订单定价链路中数据库连接池获取超时",
        ),
    ]

    decision = orchestrator._route_from_commander_output(
        payload={
            "next_mode": "single",
            "next_agent": "LogAgent",
            "should_stop": False,
            "stop_reason": "",
        },
        state={
            "discussion_step_count": 8,
            "max_discussion_steps": 10,
            "agent_outputs": {
                "JudgeAgent": {
                    "final_judgment": {
                        "root_cause": {
                            "summary": "订单定价链路中数据库连接池获取超时",
                            "confidence": 0.51,
                        }
                    }
                },
                "ProblemAnalysisAgent": {
                    "conclusion": "我已汇总各专家反馈，当前结论：订单定价链路中数据库连接池获取超时",
                    "confidence": 0.48,
                },
            },
        },
        round_cards=round_cards,
    )

    assert decision["should_stop"] is True
    assert decision["next_step"] == ""
