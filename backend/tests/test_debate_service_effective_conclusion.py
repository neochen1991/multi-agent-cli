"""test辩论服务有效结论相关测试。"""

import pytest

from app.models.debate import DebateSession, DebateStatus
from app.services.debate_service import DebateService


def _session() -> DebateSession:
    """为测试场景提供session辅助逻辑。"""
    
    return DebateSession(
        id="deb_effective_test",
        incident_id="inc_effective_test",
        status=DebateStatus.PENDING,
        context={},
    )


def test_has_effective_llm_conclusion_accepts_judge_final_judgment():
    """验证has有效LLM结论接受裁决finaljudgment。"""
    
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
    """验证has有效LLM结论拒绝降级placeholder。"""
    
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
    """验证buildresultfallbacksconfidence从rootcause。"""
    
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


def test_build_result_extracts_readable_text_from_json_wrapped_fields():
    """验证构建结果时会清洗 JSON 包裹的根因和修复建议文本。"""

    service = DebateService()
    session = _session()
    flow_result = {
        "final_judgment": {
            "root_cause": {
                "summary": """```json
                {"summary":"库存热点锁竞争放大订单事务耗时，最终拖垮连接池","category":"db_lock"}
                ```""",
                "category": "db_lock",
                "confidence": 0.68,
            },
            "fix_recommendation": {
                "summary": """{"summary":"先限制热点 SKU 并缩短库存事务"}""",
                "steps": [
                    """{"summary":"排查 t_inventory 热点行锁等待"}""",
                    "观察 Hikari 连接池 pending 指标",
                ],
            },
            "evidence_chain": [],
        },
        "action_items": ['{"summary":"先对热点 SKU 做限流"}'],
        "responsible_team": {"team": "inventory", "owner": "neo"},
    }

    result = service._build_result(session, flow_result, report={})

    assert result.root_cause == "库存热点锁竞争放大订单事务耗时，最终拖垮连接池"
    assert result.fix_recommendation is not None
    assert result.fix_recommendation.summary == "先限制热点 SKU 并缩短库存事务"
    assert result.action_items[0]["summary"] == "先对热点 SKU 做限流"


def test_build_result_prefers_meaningful_root_cause_confidence_over_stale_top_level_floor():
    """当顶层 confidence 落后于 Judge 根因置信度时，应优先保留有效根因置信度。"""

    service = DebateService()
    session = _session()
    flow_result = {
        "confidence": 0.45,
        "final_judgment": {
            "root_cause": {
                "summary": "网关路由表未包含 POST /api/v1/orders，或服务注册中心未同步 order-service 实例，导致网关层直接返回 404。",
                "category": "infrastructure.gateway-route-miss",
                "confidence": 0.68,
            },
            "evidence_chain": [
                {
                    "type": "log",
                    "description": "gateway route not found path=/api/v1/orders method=POST return=404",
                    "source": "gateway",
                    "strength": "strong",
                },
                {
                    "type": "domain",
                    "description": "接口映射确认 POST /api/v1/orders 属于 OrderController#createOrder",
                    "source": "interface_mapping",
                    "strength": "strong",
                },
            ],
        },
        "action_items": [],
        "responsible_team": {"team": "gateway-team", "owner": "alice"},
    }

    result = service._build_result(session, flow_result, report={})

    assert result.root_cause_category == "infrastructure.gateway-route-miss"
    assert result.confidence == pytest.approx(0.68, abs=1e-6)
