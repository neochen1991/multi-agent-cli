from app.runtime.autogen_runtime import AutoGenRuntimeOrchestrator


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
