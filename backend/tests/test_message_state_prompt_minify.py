"""test消息状态Promptminify相关测试。"""

from __future__ import annotations

import json

from app.runtime.langgraph.prompts import (
    build_agent_prompt,
    build_problem_analysis_commander_prompt,
)
from app.runtime.langgraph.state import AgentSpec


def _to_json(payload):
    """为测试场景提供tojson辅助逻辑。"""
    
    return json.dumps(payload, ensure_ascii=False, indent=2)


def test_commander_prompt_prefers_dialogue_summary_over_history_cards_label() -> None:
    """验证主AgentPromptprefersdialogue摘要over历史cardslabel。"""
    
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
    """验证AgentPrompt使用interaction摘要label。"""
    
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


def test_agent_prompt_includes_tool_limited_instruction() -> None:
    """验证AgentPrompt包含工具受限instruction。"""
    
    spec = AgentSpec(name="DatabaseAgent", role="数据库分析专家", phase="analysis", system_prompt="你是数据库分析专家")
    prompt = build_agent_prompt(
        spec=spec,
        loop_round=1,
        max_rounds=2,
        max_history_items=8,
        context={
            "service_name": "order-service",
            "tool_context": {
                "name": "db_snapshot_reader",
                "used": False,
                "status": "disabled",
                "summary": "数据库工具未启用",
                "command_gate": {"has_command": True, "allow_tool": True},
            },
        },
        history_cards=[],
        assigned_command={"task": "检查锁等待", "use_tool": True},
        dialogue_items=[],
        inbox_items=[],
        to_json=_to_json,
    )
    assert "工具受限说明" in prompt
    assert "继续基于已有证据推理" in prompt
    assert "不要假装已经完成实时取证" in prompt
