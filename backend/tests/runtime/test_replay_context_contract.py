"""Replay-oriented contract tests for context preparation events."""

from __future__ import annotations

import asyncio

from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=2, analysis_depth_mode="deep")


def test_agent_tool_context_prepared_event_keeps_replay_fields():
    orchestrator = _orchestrator()
    events: list[dict] = []

    async def _callback(payload: dict) -> None:
        events.append(dict(payload))

    orchestrator._event_callback = _callback
    orchestrator._input_context = {"title": "orders 502", "description": "订单接口异常"}

    asyncio.run(
        orchestrator._build_agent_context_with_tools(
            agent_name="DomainAgent",
            compact_context={
                "incident_summary": {"title": "orders 502", "description": "订单接口异常", "service_name": "order-service"},
                "interface_mapping": {
                    "matched": True,
                    "domain": "order",
                    "aggregate": "OrderAggregate",
                    "endpoint": {"path": "/api/v1/orders"},
                },
            },
            loop_round=1,
            round_number=1,
            assigned_command={"task": "确认责任田", "focus": "domain owner", "use_tool": False},
        )
    )

    prepared = [event for event in events if str(event.get("type")) == "agent_tool_context_prepared"]
    assert prepared
    payload = prepared[-1]
    assert payload["agent_name"] == "DomainAgent"
    assert "focused_preview" in payload
    assert "data_preview" in payload
    assert "command_gate" in payload
    assert "permission_decision" in payload
