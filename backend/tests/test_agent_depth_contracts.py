"""Contract tests that freeze agent depth context and tool event shapes."""

from __future__ import annotations

import asyncio

from app.runtime.langgraph.state import AgentSpec
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.services.agent_tool_context_service import agent_tool_context_service


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


def test_cross_agent_focused_context_keeps_coordination_and_verdict_sections():
    focused = agent_tool_context_service.build_focused_context(
        agent_name="ProblemAnalysisAgent",
        compact_context={
            "incident_summary": {
                "title": "orders 502",
                "description": "订单接口 502，怀疑数据库与连接池问题",
                "severity": "HIGH",
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "database_tables": ["t_order", "t_order_item"],
                "error_keywords": ["502", "timeout", "lock", "db"],
            },
        },
        incident_context={"service_name": "order-service"},
        tool_context={"name": "rule_suggestion_bundle", "status": "ok", "summary": "已汇总主控预加载证据"},
        assigned_command={
            "target_role": "problem_analysis",
            "task": "请拆解调查并在证据充分时准备最终裁决",
            "focus": "先分发，再收敛证据并给出最终判断",
        },
    )

    assert "problem_frame" in focused
    assert "investigation_focus" in focused
    assert "coordination_summary" in focused
    assert focused["coordination_summary"]["service_name"] == "order-service"
    assert focused["coordination_summary"]["dispatch_targets"]


def test_code_agent_focused_context_keeps_closure_shape():
    focused = agent_tool_context_service.build_focused_context(
        agent_name="CodeAgent",
        compact_context={
            "interface_mapping": {
                "endpoint": {
                    "method": "POST",
                    "path": "/api/v1/orders",
                    "service": "order-service",
                    "interface": "OrderController#createOrder",
                },
                "code_artifacts": ["src/order/OrderController.java"],
                "database_tables": ["t_order"],
            },
            "investigation_leads": {
                "class_names": ["OrderController", "OrderAppService"],
                "code_artifacts": ["src/order/OrderController.java"],
                "dependency_services": ["inventory-service"],
            },
        },
        incident_context={"description": "订单 502"},
        tool_context={"data": {"repo_path": "", "hits": []}},
        assigned_command={"task": "分析代码闭包", "focus": "controller -> service -> dao"},
    )

    assert "problem_entrypoint" in focused
    assert "mapped_code_scope" in focused
    assert "repo_hits" in focused
    assert "code_windows" in focused
    assert "method_call_chain" in focused
    assert isinstance(focused["analysis_expectations"], list)


def test_build_agent_context_with_tools_emits_tool_and_focused_previews():
    orchestrator = _orchestrator()
    events = []

    async def _callback(payload):
        events.append(dict(payload))

    orchestrator._event_callback = _callback
    orchestrator._input_context = {"title": "orders 502", "description": "订单接口异常"}
    compact_context = {
        "incident_summary": {"title": "orders 502", "description": "订单接口异常", "service_name": "order-service"},
        "interface_mapping": {
            "matched": True,
            "confidence": 0.99,
            "domain": "order",
            "aggregate": "OrderAggregate",
            "owner_team": "order-domain-team",
            "owner": "alice",
            "endpoint": {
                "method": "POST",
                "path": "/api/v1/orders",
                "service": "order-service",
            },
            "database_tables": ["t_order"],
        },
    }

    ctx = asyncio.run(
        orchestrator._build_agent_context_with_tools(
            agent_name="DomainAgent",
            compact_context=compact_context,
            loop_round=1,
            round_number=2,
            assigned_command={
                "task": "确认责任田和领域边界",
                "focus": "聚合根和owner team",
                "use_tool": False,
            },
        )
    )

    prepared = [item for item in events if str(item.get("type")) == "agent_tool_context_prepared"]
    assert prepared
    event = prepared[-1]
    assert event["agent_name"] == "DomainAgent"
    assert "data_preview" in event
    assert "focused_preview" in event
    assert "command_gate" in event
    assert "audit_log" in event
    assert "focused_context" in ctx
    assert ctx["focused_context"]["responsibility_mapping"]["domain"] == "order"


def test_agent_prompt_keeps_focused_context_block_contract():
    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="DatabaseAgent",
        role="数据库取证专家",
        phase="analysis",
        system_prompt="test",
    )

    prompt = orchestrator._build_agent_prompt(
        spec=spec,
        loop_round=1,
        context={
            "service": "order-service",
            "focused_context": {
                "target_tables": ["t_order", "t_order_item"],
                "causal_summary": {
                    "dominant_pattern": "lock_contention",
                    "likely_causes": ["库存扣减更新热点行竞争"],
                },
            },
        },
        history_cards=[],
        assigned_command={"task": "分析锁等待", "focus": "top sql 与 session wait"},
        dialogue_items=[],
        inbox_messages=[],
    )

    assert "Agent 专属分析上下文" in prompt
    assert "lock_contention" in prompt
