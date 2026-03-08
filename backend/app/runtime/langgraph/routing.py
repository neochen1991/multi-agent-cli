"""
路由辅助模块

本模块提供 LangGraph 辩论运行时的路由和护栏辅助函数。

路由功能说明：
- fallback_supervisor_route: 后备路由决策，当主路由失败时使用
- judge_is_ready: 判断 JudgeAgent 是否准备好执行
- recent_agent_card: 获取最近的 Agent 卡片
- recent_judge_card: 获取最近的 JudgeAgent 卡片
- round_agent_counts: 统计当前回合各 Agent 的执行次数
- route_from_commander_output: 根据 Commander 输出决定路由
- route_guardrail: 路由护栏，防止无效路由
- step_for_agent: 获取 Agent 对应的路由步骤
- supervisor_step_to_node: 将步骤转换为节点名称

设计说明：
这些函数委托给新的 routing_helpers 模块实现，保持向后兼容。

Pure routing and guardrail helpers for LangGraph debate runtime.

This module provides backward-compatible routing functions that delegate
to the new rule-based routing engine.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.runtime.messages import AgentEvidence

# 从新路由模块导入实现
from app.runtime.langgraph.routing_helpers import (  # noqa: F401
    _agent_output_from_state,
    _output_confidence,
    _recent_agent_card,
    agent_from_step,
    fallback_supervisor_route,
    judge_is_ready,
    recent_agent_card,
    recent_judge_card,
    round_agent_counts,
    route_from_commander_output,
    route_guardrail,
    step_for_agent,
    supervisor_step_to_node,
)

__all__ = [
    "_agent_output_from_state",
    "_output_confidence",
    "_recent_agent_card",
    "agent_from_step",
    "fallback_supervisor_route",
    "judge_is_ready",
    "recent_agent_card",
    "recent_judge_card",
    "round_agent_counts",
    "route_from_commander_output",
    "route_guardrail",
    "step_for_agent",
    "supervisor_step_to_node",
]