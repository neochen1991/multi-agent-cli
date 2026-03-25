"""ImpactAnalysisAgent 专项回归测试。"""

from app.runtime.langgraph.schemas.agent_output import get_schema_for_agent
from app.services.agent_tool_context_service import AgentToolContextService


def test_impact_analysis_agent_schema_exposes_rich_impact_summary():
    """验证 ImpactAnalysisAgent schema 会暴露 richer impact 字段。"""

    schema = get_schema_for_agent("ImpactAnalysisAgent")
    payload = schema().model_dump(mode="json")

    assert "impact_summary" in payload
    assert "affected_functions" in payload["impact_summary"]
    assert "affected_interfaces" in payload["impact_summary"]
    assert "affected_user_scope" in payload["impact_summary"]
    assert "unknowns" in payload["impact_summary"]


def test_impact_analysis_agent_focused_context_falls_back_to_unknowns_when_metrics_missing():
    """验证缺少量化指标时，ImpactAnalysisAgent focused context 会显式给出 unknowns。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="ImpactAnalysisAgent",
        compact_context={
            "incident_summary": {
                "title": "订单创建接口 502",
                "description": "下单流量报错升高",
                "severity": "high",
            },
            "interface_mapping": {
                "feature": "订单创建",
                "endpoint": {
                    "method": "POST",
                    "path": "/api/v1/orders",
                    "service": "order-service",
                },
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "error_keywords": ["502", "timeout"],
            },
        },
        incident_context={"description": "下单接口 502，用户创建订单失败"},
        tool_context={"data": {}},
        assigned_command={"task": "分析问题影响范围", "focus": "功能、接口和用户影响"},
    )

    assert focused["affected_functions"][0]["name"] == "订单创建"
    assert focused["affected_interfaces"][0]["endpoint"] == "/api/v1/orders"
    assert any("缺少可直接量化用户影响的监控指标" in item for item in focused["unknowns"])
