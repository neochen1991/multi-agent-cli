from datetime import datetime

from app.runtime.autogen_runtime import AutoGenRuntimeOrchestrator, DebateTurn
from app.runtime.messages import AgentEvidence


def _orchestrator() -> AutoGenRuntimeOrchestrator:
    return AutoGenRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


def test_judge_payload_recovery_from_truncated_response_keeps_root_cause():
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
            model={"name": "kimi-k2.5"},
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
            model={"name": "kimi-k2.5"},
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
