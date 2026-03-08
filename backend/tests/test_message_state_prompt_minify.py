"""test消息状态Promptminify相关测试。"""

from __future__ import annotations

import json

from app.runtime.langgraph.parsers import normalize_commander_output
from app.runtime.langgraph.prompt_builder import PromptBuilder
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


def test_commander_prompt_forbids_markdown_tables_and_requires_minimal_commands() -> None:
    """验证 commander Prompt 会明确禁止 Markdown 漂移并要求最小可执行命令。"""

    prompt = build_problem_analysis_commander_prompt(
        loop_round=1,
        max_rounds=2,
        context={"service_name": "order-service"},
        history_cards=[],
        dialogue_items=[],
        to_json=_to_json,
    )

    assert "禁止输出 Markdown 表格" in prompt
    assert "只允许输出一个 JSON 对象" in prompt
    assert "最小可执行 commands" in prompt


def test_prompt_builder_compacts_first_round_commander_context() -> None:
    """验证首轮 commander 只注入裁剪后的上下文摘要。"""

    builder = PromptBuilder(
        max_rounds=2,
        max_history_items=2,
        to_json=_to_json,
        derive_conversation_state_with_context=lambda *args, **kwargs: {},
    )
    context = {
        "incident": {
            "title": "订单提交大量 500",
            "description": "X" * 800,
            "severity": "critical",
            "service_name": "order-service",
        },
        "log_excerpt": "Y" * 1200,
        "available_analysis_agents": ["LogAgent", "CodeAgent", "DatabaseAgent", "MetricsAgent"],
        "execution_mode": "background",
        "interface_mapping": {
            "matched": True,
            "confidence": 0.93,
            "domain": "订单域",
            "aggregate": "Order",
            "owner_team": "order-sre",
            "owner": "neo",
            "database_tables": [f"public.t_table_{idx}" for idx in range(12)],
            "code_artifacts": [f"services/order/Class{idx}.java" for idx in range(10)],
            "dependency_services": [f"svc-{idx}" for idx in range(10)],
            "monitor_items": [f"metric-{idx}" for idx in range(10)],
        },
        "investigation_leads": {
            "api_endpoints": [f"POST /api/{idx}" for idx in range(8)],
            "service_names": [f"svc-{idx}" for idx in range(10)],
            "code_artifacts": [f"services/order/Class{idx}.java" for idx in range(10)],
            "class_names": [f"Class{idx}" for idx in range(10)],
            "database_tables": [f"public.t_{idx}" for idx in range(12)],
            "monitor_items": [f"metric-{idx}" for idx in range(10)],
            "dependency_services": [f"dep-{idx}" for idx in range(10)],
            "trace_ids": [f"trace-{idx}" for idx in range(8)],
            "error_keywords": [f"keyword-{idx}" for idx in range(10)],
            "domain": "订单域",
            "aggregate": "Order",
        },
        "existing_agent_outputs": {"LogAgent": {"analysis": "should not appear in round 1"}},
    }

    compact = builder._compact_commander_context(context, loop_round=1)

    assert "incident_summary" in compact
    assert "incident" not in compact
    assert "existing_agent_outputs" not in compact
    assert len(compact["interface_mapping"]["database_tables"]) == 8
    assert len(compact["investigation_leads"]["api_endpoints"]) == 4
    assert len(compact["investigation_leads"]["database_tables"]) == 8
    assert len(compact["log_excerpt"]) == 320


def test_prompt_builder_compacts_first_round_commander_context_with_summary_fallbacks() -> None:
    """验证 commander 压缩上下文能从 incident_summary 和顶层字段兜底取值。"""

    builder = PromptBuilder(
        max_rounds=2,
        max_history_items=2,
        to_json=_to_json,
        derive_conversation_state_with_context=lambda *args, **kwargs: {},
    )
    compact = builder._compact_commander_context(
        {
            "incident_summary": {
                "title": "订单服务大量 500",
                "description": "库存锁等待放大事务耗时",
                "severity": "critical",
                "service_name": "order-service",
            },
            "execution_mode": "background",
            "parallel_analysis_agents": ["LogAgent", "DatabaseAgent", "MetricsAgent"],
        },
        loop_round=1,
    )

    assert compact["incident_summary"]["title"] == "订单服务大量 500"
    assert compact["incident_summary"]["service_name"] == "order-service"
    assert compact["available_analysis_agents"] == ["LogAgent", "DatabaseAgent", "MetricsAgent"]
    assert compact["execution_mode"] == "background"


def test_normalize_commander_output_recovers_commands_from_markdown_table() -> None:
    """验证 commander 漂成 Markdown 表格时仍能回收出最小命令。"""

    raw_content = """
我的判断是：先并行排查数据库与日志。

| **target_agent** | **task** | **focus** | **expected_output** | **use_tool** | **database_tables** | **skill_hints** |
|:---|:---|:---|:---|:---|:---|:---|
| DatabaseAgent | 检查锁等待和慢 SQL | t_order / t_inventory | 输出锁等待链路 | true | public.t_order, public.t_inventory | postgres-lock-check |
| LogAgent | 重建错误时间线 | POST /api/v1/orders | 输出 500 时间窗与 trace | true |  | log-timeline |
"""

    normalized = normalize_commander_output({}, raw_content)

    assert len(normalized["commands"]) == 2
    assert normalized["commands"][0]["target_agent"] == "DatabaseAgent"
    assert normalized["commands"][0]["use_tool"] is True
    assert normalized["commands"][0]["database_tables"] == ["public.t_order", "public.t_inventory"]
    assert normalized["commands"][0]["skill_hints"] == ["postgres-lock-check"]
    assert normalized["commands"][1]["target_agent"] == "LogAgent"
