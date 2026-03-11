"""Agent context envelope contracts for prompt rendering."""

from __future__ import annotations

import json

from app.runtime.langgraph.prompts import build_peer_driven_prompt
from app.runtime.langgraph.state import AgentSpec


def test_peer_driven_prompt_prefers_context_envelope_over_raw_incident_dump():
    prompt = build_peer_driven_prompt(
        spec=AgentSpec(name="DatabaseAgent", role="数据库专家", phase="analysis", system_prompt=""),
        loop_round=1,
        max_rounds=2,
        context={
            "shared_context": {
                "incident_summary": {"title": "orders 502", "service_name": "order-service"},
                "interface_mapping": {"database_tables": ["t_order"]},
            },
            "focused_context": {"target_tables": ["t_order"], "causal_summary": {"dominant_pattern": "lock_wait"}},
            "tool_context": {"name": "db_snapshot_reader", "status": "ok"},
            "peer_context": [{"agent": "LogAgent", "summary": "lock wait"}],
            "mailbox_context": [{"sender": "ProblemAnalysisAgent", "message_type": "command"}],
            "incident": {"description": "RAW_INCIDENT_SHOULD_NOT_APPEAR"},
        },
        skill_context={"phases": ["evidence_collection"]},
        peer_items=[{"agent": "LogAgent", "summary": "lock wait"}],
        assigned_command={"task": "分析锁等待", "focus": "top sql"},
        inbox_items=[{"sender": "ProblemAnalysisAgent", "message_type": "command"}],
        to_json=json.dumps,
    )

    assert "共享上下文" in prompt
    assert "RAW_INCIDENT_SHOULD_NOT_APPEAR" not in prompt
    assert '"shared_context"' not in prompt
