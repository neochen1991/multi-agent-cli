"""test裁决载荷恢复相关测试。"""

from datetime import datetime

from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator, DebateTurn
from app.runtime.messages import AgentEvidence


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    """为测试场景提供orchestrator辅助逻辑。"""
    
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


def test_judge_payload_recovery_from_truncated_response_keeps_root_cause():
    """验证裁决载荷恢复从truncatedresponse保留rootcause。"""
    
    orchestrator = _orchestrator()
    raw = """```json
{
  "final_judgment": {
    "root_cause": {
      "summary": "HikariCP连接获取超时（池压力）",
      "category": "infrastructure_resource_exhaustion",
      "confidence": 0.78
    },
    "evidence_chain": [
      {"type": "log", "description": "连接获取超时", "source": "CodeAgent", "strength": "strong"}
    ],
    "fix_recommendation": {
      "summary": "先采集连接池指标",
      "steps": ["采集 active/idle/waiting"],
      "code_changes_required": false
    },
    "impact_analysis": {"affected_services": ["order-service"], "business_impact": "下单失败"},
    "risk_assessment": {"risk_level": "high", "risk_factors": ["连接池资源不足"]}
  },
  "decision_rationale": {"reasoning": "综合结论
```"""

    payload = orchestrator._normalize_agent_output("JudgeAgent", raw)

    assert payload["final_judgment"]["root_cause"]["summary"] == "HikariCP连接获取超时（池压力）"
    assert payload["final_judgment"]["root_cause"]["category"] == "infrastructure_resource_exhaustion"
    assert payload["confidence"] >= 0.75


def test_judge_payload_recovery_wraps_nested_final_judgment_object():
    """验证裁决载荷恢复wrapsnestedfinaljudgmentobject。"""
    
    orchestrator = _orchestrator()
    raw = (
        '{"root_cause":{"summary":"数据库连接池耗尽","category":"db_pool","confidence":0.82},'
        '"evidence_chain":["连接获取超时30s"],'
        '"fix_recommendation":{"summary":"排查连接泄漏","steps":["检查连接关闭"],"code_changes_required":false},'
        '"risk_assessment":{"risk_level":"high","risk_factors":["连接池资源不足"]},'
        '"confidence":0.82}'
    )

    payload = orchestrator._normalize_agent_output("JudgeAgent", raw)

    assert payload["final_judgment"]["root_cause"]["summary"] == "数据库连接池耗尽"
    assert payload["confidence"] == 0.82


def test_build_final_payload_uses_best_agent_conclusion_when_judge_fallback():
    """验证buildfinal载荷使用bestAgent结论当裁决回退。"""
    
    orchestrator = _orchestrator()
    now = datetime.utcnow()
    code_output = {
        "analysis": "连接池等待队列增长，事务耗时过长",
        "conclusion": "订单创建链路出现连接池耗尽，需收敛事务边界并调优连接池配置",
        "evidence_chain": ["HikariPool timeout 30000ms", "OrderAppService#createOrder costMs=30058"],
        "confidence": 0.91,
    }
    judge_fallback = orchestrator._normalize_judge_output({}, "JudgeAgent 调用超时，已降级继续")

    orchestrator.turns = [
        DebateTurn(
            round_number=1,
            phase="analysis",
            agent_name="CodeAgent",
            agent_role="代码分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=code_output,
            confidence=0.91,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=2,
            phase="judgment",
            agent_name="JudgeAgent",
            agent_role="技术委员会主席",
            model={"name": "glm-5"},
            input_message="",
            output_content=judge_fallback,
            confidence=0.5,
            started_at=now,
            completed_at=now,
        ),
    ]
    history_cards = [
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码侧判断连接池等待过长",
            conclusion=code_output["conclusion"],
            evidence_chain=code_output["evidence_chain"],
            confidence=0.91,
            raw_output=code_output,
        )
    ]

    payload = orchestrator._build_final_payload(
        history_cards=history_cards,
        consensus_reached=False,
        executed_rounds=1,
    )

    summary = payload["final_judgment"]["root_cause"]["summary"]
    assert summary != orchestrator.JUDGE_FALLBACK_SUMMARY
    assert "连接池" in summary
    assert payload["confidence"] >= 0.55


def test_build_final_payload_caps_confidence_when_key_evidence_is_degraded():
    """验证buildfinal载荷capsconfidence当key证据is降级。"""
    
    orchestrator = _orchestrator()
    now = datetime.utcnow()
    judge_output = {
        "chat_message": "当前方向先按连接池耗尽处理。",
        "final_judgment": {
            "root_cause": {
                "summary": "连接池耗尽导致订单创建超时",
                "category": "db_resource_exhaustion",
                "confidence": 0.82,
            },
            "evidence_chain": [{"type": "analysis", "description": "单点日志证据", "source": "JudgeAgent"}],
            "fix_recommendation": {"summary": "先扩容", "steps": ["扩容连接池"], "code_changes_required": False},
            "impact_analysis": {"affected_services": ["order-service"], "business_impact": "下单失败"},
            "risk_assessment": {"risk_level": "medium", "risk_factors": []},
        },
        "decision_rationale": {"reasoning": "暂按已有方向收敛"},
        "action_items": [],
        "responsible_team": {"team": "order", "owner": "neo"},
        "confidence": 0.82,
    }
    orchestrator.turns = [
        DebateTurn(
            round_number=1,
            phase="analysis",
            agent_name="LogAgent",
            agent_role="日志分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content={
                "conclusion": "LogAgent 调用超时，已降级继续",
                "confidence": 0.45,
                "degraded": True,
                "evidence_status": "degraded",
            },
            confidence=0.45,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=2,
            phase="analysis",
            agent_name="DatabaseAgent",
            agent_role="数据库分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content={
                "conclusion": "DatabaseAgent 证据未采集完成：数据库工具未启用",
                "confidence": 0.22,
                "degraded": True,
                "evidence_status": "missing",
                "tool_status": "disabled",
            },
            confidence=0.22,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=3,
            phase="judgment",
            agent_name="JudgeAgent",
            agent_role="技术委员会主席",
            model={"name": "glm-5"},
            input_message="",
            output_content=judge_output,
            confidence=0.82,
            started_at=now,
            completed_at=now,
        ),
    ]
    history_cards = [
        AgentEvidence(
            agent_name="LogAgent",
            phase="analysis",
            summary="日志侧未完成",
            conclusion="LogAgent 调用超时，已降级继续",
            evidence_chain=[],
            confidence=0.45,
            raw_output=orchestrator.turns[0].output_content,
        ),
        AgentEvidence(
            agent_name="DatabaseAgent",
            phase="analysis",
            summary="数据库证据缺失",
            conclusion="DatabaseAgent 证据未采集完成：数据库工具未启用",
            evidence_chain=[],
            confidence=0.22,
            raw_output=orchestrator.turns[1].output_content,
        ),
    ]

    payload = orchestrator._build_final_payload(
        history_cards=history_cards,
        consensus_reached=False,
        executed_rounds=1,
    )

    assert payload["confidence"] <= 0.45
    risk_factors = payload["final_judgment"]["risk_assessment"]["risk_factors"]
    assert any("关键证据不足" in item for item in risk_factors)
