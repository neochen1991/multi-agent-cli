"""
Graph Builder
动态图构建器

从配置动态构建 LangGraph 图节点，而非硬编码。
支持：
- 根据AgentSpec动态添加Agent节点
- 配置驱动的图构建
- 灵活的路由配置

使用方式：
    builder = GraphBuilder(orchestrator)
    agent_specs = orchestrator._agent_sequence()
    graph = builder.build(agent_specs)
    app = graph.compile(checkpointer=checkpointer)
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import structlog
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.runtime.langgraph.state import AgentSpec, DebateExecState
from app.runtime.langgraph.nodes import (
    build_agent_node,
    build_finalize_node,
    build_init_session_node,
    build_phase_handler_node,
    build_round_evaluate_node,
    build_round_start_node,
    build_supervisor_node,
)

if TYPE_CHECKING:
    from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator

logger = structlog.get_logger()


class GraphBuilder:
    """
    动态图构建器

    从配置动态构建 LangGraph 图，支持：
    - 根据AgentSpec列表动态添加Agent节点
    - 根据配置决定是否启用协作/批判环节
    - 统一的路由配置

    图结构：
    START -> init_session -> round_start -> supervisor_decide
                                              |
                                              v
                                +-------------------------------+
                                |    动态Agent节点 / 并行节点    |
                                +-------------------------------+
                                              |
                                              v
                                       round_evaluate
                                              |
                                              v
                               +------------------------+
                               | round_start | finalize |
                               +------------------------+
    """

    # 核心节点名称常量
    NODE_INIT_SESSION = "init_session"
    NODE_ROUND_START = "round_start"
    NODE_SUPERVISOR_DECIDE = "supervisor_decide"
    NODE_ROUND_EVALUATE = "round_evaluate"
    NODE_FINALIZE = "finalize"

    # 动态节点名称前缀
    NODE_ANALYSIS_PARALLEL = "analysis_parallel_node"
    NODE_ANALYSIS_COLLABORATION = "analysis_collaboration_node"
    NODE_AGENT_SUFFIX = "_agent_node"

    def __init__(self, orchestrator: "LangGraphRuntimeOrchestrator"):
        """
        初始化图构建器。

        Args:
            orchestrator: LangGraphRuntimeOrchestrator 实例
        """
        self._orchestrator = orchestrator

    def build(self, agent_specs: List[AgentSpec]) -> StateGraph:
        """
        构建完整的 LangGraph 图。

        Args:
            agent_specs: AgentSpec 列表

        Returns:
            编译后的 StateGraph
        """
        graph = StateGraph(DebateExecState)

        # 1. 添加核心节点
        self._add_core_nodes(graph)

        # 2. 动态添加Agent节点
        route_table = self._add_agent_nodes(graph, agent_specs)

        # 3. 添加并行/协作节点
        self._add_phase_nodes(graph)

        # 4. 添加边
        self._add_edges(graph, route_table)

        logger.info(
            "graph_built",
            session_id=self._orchestrator.session_id,
            agent_count=len(agent_specs),
            route_table_keys=list(route_table.keys()),
        )

        return graph

    def _add_core_nodes(self, graph: StateGraph) -> None:
        """添加核心节点"""
        graph.add_node(self.NODE_INIT_SESSION, build_init_session_node(self._orchestrator))
        graph.add_node(self.NODE_ROUND_START, build_round_start_node(self._orchestrator))
        graph.add_node(self.NODE_SUPERVISOR_DECIDE, build_supervisor_node(self._orchestrator))
        graph.add_node(self.NODE_ROUND_EVALUATE, build_round_evaluate_node(self._orchestrator))
        graph.add_node(self.NODE_FINALIZE, build_finalize_node(self._orchestrator))

    def _add_agent_nodes(
        self,
        graph: StateGraph,
        agent_specs: List[AgentSpec],
    ) -> Dict[str, str]:
        """
        动态添加Agent节点。

        Args:
            graph: StateGraph 实例
            agent_specs: AgentSpec 列表

        Returns:
            路由表映射 {节点名称: 节点名称}
        """
        route_table: Dict[str, str] = {
            self.NODE_ROUND_EVALUATE: self.NODE_ROUND_EVALUATE,
            self.NODE_FINALIZE: self.NODE_FINALIZE,
        }

        # 按 phase 分组 Agent
        agents_by_phase: Dict[str, List[AgentSpec]] = {}
        for spec in agent_specs:
            phase = spec.phase
            if phase not in agents_by_phase:
                agents_by_phase[phase] = []
            agents_by_phase[phase].append(spec)

        # 添加所有Agent节点
        for spec in agent_specs:
            node_name = self._agent_to_node_name(spec.name)
            graph.add_node(node_name, build_agent_node(self._orchestrator, spec.name))
            route_table[node_name] = node_name

            logger.debug(
                "agent_node_added",
                agent_name=spec.name,
                node_name=node_name,
                phase=spec.phase,
            )

        return route_table

    def _add_phase_nodes(self, graph: StateGraph) -> None:
        """添加并行分析/协作阶段节点"""
        # 并行分析节点
        graph.add_node(
            self.NODE_ANALYSIS_PARALLEL,
            build_phase_handler_node(self._orchestrator, "_graph_analysis_parallel"),
        )

        # 协作节点（可选）
        if settings.DEBATE_ENABLE_COLLABORATION:
            graph.add_node(
                self.NODE_ANALYSIS_COLLABORATION,
                build_phase_handler_node(self._orchestrator, "_graph_analysis_collaboration"),
            )

    def _add_edges(
        self,
        graph: StateGraph,
        route_table: Dict[str, str],
    ) -> None:
        """
        添加图边。

        Args:
            graph: StateGraph 实例
            route_table: 路由表映射
        """
        # 入口边
        graph.add_edge(START, self.NODE_INIT_SESSION)
        graph.add_edge(self.NODE_INIT_SESSION, self.NODE_ROUND_START)
        graph.add_edge(self.NODE_ROUND_START, self.NODE_SUPERVISOR_DECIDE)

        # 并行/协作节点边
        graph.add_edge(self.NODE_ANALYSIS_PARALLEL, self.NODE_SUPERVISOR_DECIDE)
        if settings.DEBATE_ENABLE_COLLABORATION:
            graph.add_edge(self.NODE_ANALYSIS_COLLABORATION, self.NODE_SUPERVISOR_DECIDE)

        # Agent节点边 -> supervisor_decide
        for node_name in route_table:
            if node_name.endswith(self.NODE_AGENT_SUFFIX):
                graph.add_edge(node_name, self.NODE_SUPERVISOR_DECIDE)

        # 条件路由：supervisor_decide -> 各Agent节点
        route_table[self.NODE_ANALYSIS_PARALLEL] = self.NODE_ANALYSIS_PARALLEL
        if settings.DEBATE_ENABLE_COLLABORATION:
            route_table[self.NODE_ANALYSIS_COLLABORATION] = self.NODE_ANALYSIS_COLLABORATION

        graph.add_conditional_edges(
            self.NODE_SUPERVISOR_DECIDE,
            self._orchestrator._route_after_supervisor_decide,
            route_table,
        )

        # 条件路由：round_evaluate -> round_start / finalize
        graph.add_conditional_edges(
            self.NODE_ROUND_EVALUATE,
            self._orchestrator._route_after_round_evaluate,
            {
                self.NODE_ROUND_START: self.NODE_ROUND_START,
                self.NODE_FINALIZE: self.NODE_FINALIZE,
            },
        )

        # 出口边
        graph.add_edge(self.NODE_FINALIZE, END)

    def _agent_to_node_name(self, agent_name: str) -> str:
        """
        将Agent名称转换为节点名称。

        Args:
            agent_name: Agent名称（如 LogAgent）

        Returns:
            节点名称（如 log_agent_node）
        """
        predefined = {
            "LogAgent": "log_agent_node",
            "DomainAgent": "domain_agent_node",
            "CodeAgent": "code_agent_node",
            "CriticAgent": "critic_agent_node",
            "RebuttalAgent": "rebuttal_agent_node",
            "JudgeAgent": "judge_agent_node",
        }
        if agent_name in predefined:
            return predefined[agent_name]
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", str(agent_name or "").strip()).lower()
        return f"{snake}{self.NODE_AGENT_SUFFIX}"

    def get_route_table(self, agent_specs: List[AgentSpec]) -> Dict[str, str]:
        """
        获取完整的路由表。

        Args:
            agent_specs: AgentSpec 列表

        Returns:
            路由表映射
        """
        route_table: Dict[str, str] = {
            self.NODE_ROUND_EVALUATE: self.NODE_ROUND_EVALUATE,
            self.NODE_FINALIZE: self.NODE_FINALIZE,
            self.NODE_ANALYSIS_PARALLEL: self.NODE_ANALYSIS_PARALLEL,
        }

        if settings.DEBATE_ENABLE_COLLABORATION:
            route_table[self.NODE_ANALYSIS_COLLABORATION] = self.NODE_ANALYSIS_COLLABORATION

        for spec in agent_specs:
            node_name = self._agent_to_node_name(spec.name)
            route_table[node_name] = node_name

        return route_table


__all__ = [
    "GraphBuilder",
]
