import pytest

from app.models.debate import DebateSession, DebateStatus
from app.services.debate_service import DebateService


def _session() -> DebateSession:
    return DebateSession(
        id="deb_effective_test",
        incident_id="inc_effective_test",
        status=DebateStatus.PENDING,
        context={},
    )


def test_has_effective_llm_conclusion_accepts_judge_final_judgment():
    service = DebateService()
    debate_result = {
        "confidence": 0.74,
        "final_judgment": {
            "root_cause": {
                "summary": "订单服务连接池被耗尽，导致事务开启失败",
                "category": "runtime_log",
                "confidence": 0.74,
            },
            "evidence_chain": [
                {"type": "log", "description": "HikariPool timeout after 30000ms", "source": "log"},
                {"type": "code", "description": "OrderAppService 事务跨度过大", "source": "code"},
            ],
        },
        "debate_history": [
            {
                "agent_name": "JudgeAgent",
                "confidence": 0.74,
                "output_content": {
                    "final_judgment": {
                        "root_cause": {"summary": "订单服务连接池被耗尽，导致事务开启失败"}
                    }
                },
            }
        ],
    }
    assert service._has_effective_llm_conclusion(debate_result)


def test_has_effective_llm_conclusion_rejects_degraded_placeholder():
    service = DebateService()
    debate_result = {
        "confidence": 0.86,
        "final_judgment": {
            "root_cause": {
                "summary": "LLM 服务繁忙，已降级为规则分析：POST /api/v1/orders 存在故障",
                "category": "degraded_rule_based",
                "confidence": 0.86,
            },
            "evidence_chain": [
                {"type": "system", "description": "LLM 调用超时触发降级", "source": "degrade_fallback"},
            ],
        },
        "debate_history": [
            {"agent_name": "JudgeAgent", "confidence": 0.86, "output_content": {}},
        ],
    }
    assert not service._has_effective_llm_conclusion(debate_result)


def test_build_result_fallbacks_confidence_from_root_cause():
    service = DebateService()
    session = _session()
    flow_result = {
        "final_judgment": {
            "root_cause": {
                "summary": "数据库连接池耗尽导致订单创建事务无法开启",
                "category": "runtime_log",
                "confidence": 0.72,
            },
            "evidence_chain": [
                {
                    "type": "log",
                    "description": "HikariPool-1 request timed out after 30000ms",
                    "source": "log",
                    "strength": "strong",
                }
            ],
        },
        "action_items": [],
        "responsible_team": {"team": "order-domain-team", "owner": "alice"},
    }

    result = service._build_result(session, flow_result, report={})
    assert result.root_cause == "数据库连接池耗尽导致订单创建事务无法开启"
    assert result.root_cause_category == "runtime_log"
    assert result.confidence == pytest.approx(0.72, abs=1e-6)
