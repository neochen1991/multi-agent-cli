"""Prompt builder tests for message-state focused context."""

from __future__ import annotations

import json

from app.runtime.langgraph.prompts import (
    build_agent_prompt,
    build_problem_analysis_commander_prompt,
)
from app.runtime.langgraph.state import AgentSpec


def _to_json(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2)


def test_commander_prompt_prefers_dialogue_summary_over_history_cards_label() -> None:
    prompt = build_problem_analysis_commander_prompt(
        loop_round=1,
        max_rounds=2,
        context={"service_name": "order-service"},
        history_cards=[],
        dialogue_items=[
            {"agent_name": "LogAgent", "phase": "analysis", "message": "发现 502 与连接池耗尽同时出现", "confidence": 0.8}
        ],
        to_json=_to_json,
    )
    assert "已有观点卡片" not in prompt
    assert "最近发言摘要" in prompt
    assert "最近对话消息" in prompt


def test_agent_prompt_uses_interaction_summary_label() -> None:
    spec = AgentSpec(name="CodeAgent", role="代码分析专家", phase="analysis", system_prompt="你是代码分析专家")
    prompt = build_agent_prompt(
        spec=spec,
        loop_round=1,
        max_rounds=2,
        max_history_items=8,
        context={"service_name": "order-service"},
        history_cards=[],
        assigned_command={"task": "分析连接池耗尽代码路径"},
        dialogue_items=[{"agent_name": "ProblemAnalysisAgent", "phase": "analysis", "message": "请你检查事务边界"}],
        inbox_items=[],
        to_json=_to_json,
    )
    assert "最近结论卡片" not in prompt
    assert "最近交互摘要" in prompt
    assert "最近对话消息" in prompt

