"""
路由服务模块

本模块提供编排级别的路由决策封装。

核心功能：
1. 分析阶段后的路由决策
2. 批评阶段后的路由决策
3. 监督者决策后的路由
4. 回合评估后的路由
5. 预算计算

路由决策：
- analysis_collaboration: 分析协作
- critic: 批评
- rebuttal: 反驳
- judge: 裁决
- round_start: 回合开始
- finalize: 结束

使用场景：
- 编排器根据状态决定下一步
- 计算讨论预算
- 映射步骤到节点

Routing service for orchestration-level route decisions.
"""

from __future__ import annotations

from typing import Any, Dict

from app.runtime.langgraph.routing import (
    agent_from_step as agent_from_step_route,
    step_for_agent as step_for_agent_route,
    supervisor_step_to_node as supervisor_step_to_node_route,
)


class RoutingService:
    """
    路由服务

    封装编排器使用的路由决策辅助函数。

    功能：
    - 根据配置决定路由方向
    - 映射步骤到节点
    - 计算讨论预算
    """

    @staticmethod
    def route_after_analysis_parallel(*, enable_collaboration: bool) -> str:
        """
        分析并行后的路由决策

        Args:
            enable_collaboration: 是否启用协作

        Returns:
            str: 下一个节点名称
        """
        return "analysis_collaboration" if bool(enable_collaboration) else "critic"

    @staticmethod
    def route_after_critic(*, enable_critique: bool) -> str:
        """
        批评后的路由决策

        Args:
            enable_critique: 是否启用批评

        Returns:
            str: 下一个节点名称
        """
        return "rebuttal" if bool(enable_critique) else "judge"

    @staticmethod
    def supervisor_step_to_node(next_step: str) -> str:
        """
        监督者步骤到节点的映射

        Args:
            next_step: 下一步标识

        Returns:
            str: 节点名称
        """
        return supervisor_step_to_node_route(next_step)

    def route_after_supervisor_decide(self, state: Dict[str, Any]) -> str:
        """
        监督者决策后的路由

        Args:
            state: 当前状态

        Returns:
            str: 下一个节点名称
        """
        return self.supervisor_step_to_node(str((state or {}).get("next_step") or ""))

    @staticmethod
    def route_after_round_evaluate(state: Dict[str, Any]) -> str:
        """
        回合评估后的路由

        Args:
            state: 当前状态

        Returns:
            str: 下一个节点名称
        """
        return "round_start" if bool((state or {}).get("continue_next_round")) else "finalize"

    @staticmethod
    def round_discussion_budget(
        *,
        base_steps: int,
        enable_collaboration: bool,
        enable_critique: bool,
    ) -> int:
        """
        计算回合讨论预算

        根据配置计算最大讨论步数。

        Args:
            base_steps: 基础步数
            enable_collaboration: 是否启用协作
            enable_critique: 是否启用批评

        Returns:
            int: 最大讨论步数
        """
        base = int(base_steps or 0)
        if bool(enable_collaboration):
            base += 2
        if not bool(enable_critique):
            base = max(4, base - 2)
        return max(4, min(base, 24))

    @staticmethod
    def step_for_agent(agent_name: str) -> str:
        """
        Agent 名称到步骤的映射

        Args:
            agent_name: Agent 名称

        Returns:
            str: 步骤标识
        """
        return step_for_agent_route(agent_name)

    @staticmethod
    def agent_from_step(step: str) -> str:
        """
        步骤到 Agent 名称的映射

        Args:
            step: 步骤标识

        Returns:
            str: Agent 名称
        """
        return agent_from_step_route(step)