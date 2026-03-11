"""Prompt mode contracts for independent-first expert analysis."""

from __future__ import annotations

import json

from app.runtime.langgraph.prompts import build_peer_driven_prompt
from app.runtime.langgraph.state import AgentSpec


def test_first_wave_analysis_prompt_allows_independent_evidence_collection():
    prompt = build_peer_driven_prompt(
        spec=AgentSpec(name="CodeAgent", role="代码专家", phase="analysis", system_prompt=""),
        loop_round=1,
        max_rounds=4,
        context={"shared_context": {"incident_summary": {"title": "orders 502"}}},
        skill_context=None,
        peer_items=[],
        assigned_command={"task": "定位代码闭包", "focus": "controller -> service -> dao"},
        to_json=json.dumps,
    )

    assert "禁止独立分析" not in prompt
    assert "先基于你的专属上下文独立取证" in prompt
