"""
Graph Builder - 动态图构建器

本模块负责动态构建 LangGraph 状态图，实现多 Agent 协作的流程编排。

核心功能：
1. 根据配置动态构建图节点，而非硬编码
2. 根据 AgentSpec 列表动态添加 Agent 节点
3. 支持并行分析和协作模式
4. 灵活的条件路由配置

图结构示意：
```
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
```

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
from app.runtime.langgraph.checkpointer import create_checkpointer
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

    负责根据配置动态构建 LangGraph 状态图，支持：
    - 根据 AgentSpec 列表动态添加 Agent 节点
    - 根据配置决定是否启用协作/批判环节
    - 统一的路由配置

    核心节点说明：
    - init_session: 初始化会话，设置初始状态
    - round_start: 回合开始，递增 current_round
    - supervisor_decide: 路由决策，决定下一步执行哪个节点
    - round_evaluate: 回合评估，判断是否达成共识或继续下一回合
    - finalize: 最终处理，生成报告

    动态节点：
    - analysis_parallel_node: 并行执行多个分析 Agent
    - analysis_collaboration_node: Agent 间协作节点
    - {agent_name}_agent_node: 单个 Agent 执行节点
    """

    # 核心节点名称常量
    NODE_INIT_SESSION = "init_session"  # 会话初始化节点
    NODE_ROUND_START = "round_start"  # 回合开始节点
    NODE_SUPERVISOR_DECIDE = "supervisor_decide"  # 路由决策节点
    NODE_ROUND_EVALUATE = "round_evaluate"  # 回合评估节点
    NODE_FINALIZE = "finalize"  # 最终处理节点

    # 动态节点名称前缀
    NODE_ANALYSIS_PARALLEL = "analysis_parallel_node"  # 并行分析节点
    NODE_ANALYSIS_COLLABORATION = "analysis_collaboration_node"  # 协作节点
    NODE_AGENT_SUFFIX = "_agent_node"  # Agent 节点后缀

    def __init__(self, orchestrator: "LangGraphRuntimeOrchestrator"):
        """
        初始化图构建器。

        Args:
            orchestrator: LangGraphRuntimeOrchestrator 实例
        """
        self._orchestrator = orchestrator

    def build(self, agent_specs: List[AgentSpec]) -> StateGraph:
        """
        构建完整的 LangGraph 状态图

        构建流程：
        1. 创建 StateGraph 实例，指定状态类型为 DebateExecState
        2. 添加核心节点（init_session, round_start, supervisor_decide 等）
        3. 根据 AgentSpec 列表动态添加 Agent 节点
        4. 添加并行/协作阶段节点
        5. 添加边和条件路由

        Args:
            agent_specs: AgentSpec 列表，定义要添加的 Agent

        Returns:
            StateGraph: 构建完成的状态图（需编译后使用）
        """
        # 先创建空图，再按“核心节点 -> 动态 Agent 节点 -> 阶段节点 -> 边”的顺序装配。
        # 这样切换 deployment/profile 时，只需要替换 AgentSpec 集合即可重建整张图。
        graph = StateGraph(DebateExecState)

        # 1. 添加核心节点
        self._add_core_nodes(graph)

        # 2. 动态添加 Agent 节点，返回路由表
        route_table = self._add_agent_nodes(graph, agent_specs)

        # 3. 添加并行/协作阶段节点
        self._add_phase_nodes(graph)

        # 4. 添加边和条件路由
        self._add_edges(graph, route_table)

        logger.info(
            "graph_built",
            session_id=self._orchestrator.session_id,
            agent_count=len(agent_specs),
            route_table_keys=list(route_table.keys()),
        )

        return graph

    def _add_core_nodes(self, graph: StateGraph) -> None:
        """
        添加核心节点

        核心节点是所有辩论流程必须的节点：
        - init_session: 初始化会话状态
        - round_start: 回合开始处理
        - supervisor_decide: 路由决策中心
        - round_evaluate: 回合结束评估
        - finalize: 最终处理和报告生成

        Args:
            graph: StateGraph 实例
        """
        # 核心节点是所有会话都必须存在的骨架，不受当前 Agent 列表开关影响。
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
        动态添加 Agent 节点

        根据 AgentSpec 列表为每个 Agent 创建对应的图节点。
        节点名称格式：{agent_name_snake_case}_agent_node

        Args:
            graph: StateGraph 实例
            agent_specs: AgentSpec 列表

        Returns:
            Dict[str, str]: 路由表映射 {节点名称: 节点名称}
        """
        # route_table 保存“逻辑下一步”到“真实图节点名”的映射，供 supervisor 条件边复用。
        route_table: Dict[str, str] = {
            self.NODE_ROUND_EVALUATE: self.NODE_ROUND_EVALUATE,
            self.NODE_FINALIZE: self.NODE_FINALIZE,
        }

        # 先按 phase 粗分一遍，方便后续扩展按阶段批量装配或治理统计。
        agents_by_phase: Dict[str, List[AgentSpec]] = {}
        for spec in agent_specs:
            phase = spec.phase
            if phase not in agents_by_phase:
                agents_by_phase[phase] = []
            agents_by_phase[phase].append(spec)

        # 每个 Agent 都会被包装成一个独立 LangGraph 节点，
        # supervisor 后续只需要返回 node_name 即可把图推进到对应专家。
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
        """
        添加阶段处理节点

        包括：
        - analysis_parallel: 并行执行多个分析 Agent
        - analysis_collaboration: Agent 间协作（可选）

        Args:
            graph: StateGraph 实例
        """
        # 并行分析节点：由 PhaseExecutor 负责把多个 analysis Agent 分批跑起来。
        graph.add_node(
            self.NODE_ANALYSIS_PARALLEL,
            build_phase_handler_node(self._orchestrator, "_graph_analysis_parallel"),
        )

        # 协作节点只在当前运行策略显式开启时挂载，避免不用的节点混进图里。
        if bool(getattr(self._orchestrator, "_enable_collaboration", False)):
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
        添加图边和条件路由

        构建图的连接关系：
        1. 入口边：START -> init_session -> round_start -> supervisor_decide
        2. 并行/协作节点边：返回到 supervisor_decide
        3. Agent 节点边：返回到 supervisor_decide
        4. 条件路由：supervisor_decide 根据状态决定下一个节点
        5. 条件路由：round_evaluate 决定继续下一回合或结束
        6. 出口边：finalize -> END

        Args:
            graph: StateGraph 实例
            route_table: 路由表映射
        """
        # 入口骨架固定不变：会话初始化 -> 新一轮开始 -> supervisor 决策。
        graph.add_edge(START, self.NODE_INIT_SESSION)
        graph.add_edge(self.NODE_INIT_SESSION, self.NODE_ROUND_START)
        graph.add_edge(self.NODE_ROUND_START, self.NODE_SUPERVISOR_DECIDE)

        # 阶段节点完成后不直接结束，而是统一回到 supervisor 继续决策下一跳。
        graph.add_edge(self.NODE_ANALYSIS_PARALLEL, self.NODE_SUPERVISOR_DECIDE)
        if bool(getattr(self._orchestrator, "_enable_collaboration", False)):
            graph.add_edge(self.NODE_ANALYSIS_COLLABORATION, self.NODE_SUPERVISOR_DECIDE)

        # 单个专家节点执行完也统一回 supervisor，避免在图上硬编码专家间互跳。
        for node_name in route_table:
            if node_name.endswith(self.NODE_AGENT_SUFFIX):
                graph.add_edge(node_name, self.NODE_SUPERVISOR_DECIDE)

        # 将阶段节点加入 route_table，供 supervisor 直接跳转。
        route_table[self.NODE_ANALYSIS_PARALLEL] = self.NODE_ANALYSIS_PARALLEL
        if bool(getattr(self._orchestrator, "_enable_collaboration", False)):
            route_table[self.NODE_ANALYSIS_COLLABORATION] = self.NODE_ANALYSIS_COLLABORATION

        # supervisor 只产出抽象 next_step；真正映射到哪个节点，由 route_table 决定。
        graph.add_conditional_edges(
            self.NODE_SUPERVISOR_DECIDE,
            self._orchestrator._route_after_supervisor_decide,  # 路由决策函数
            route_table,
        )

        # round_evaluate 是每轮唯一收口点：继续下一轮或直接 finalize。
        graph.add_conditional_edges(
            self.NODE_ROUND_EVALUATE,
            self._orchestrator._route_after_round_evaluate,  # 路由决策函数
            {
                self.NODE_ROUND_START: self.NODE_ROUND_START,
                self.NODE_FINALIZE: self.NODE_FINALIZE,
            },
        )

        # 出口边：finalize -> END
        graph.add_edge(self.NODE_FINALIZE, END)

    def _agent_to_node_name(self, agent_name: str) -> str:
        """
        将 Agent 名称转换为节点名称

        转换规则：
        1. 预定义的 Agent 使用固定映射
        2. 其他 Agent 使用驼峰转蛇形命名 + 后缀

        Args:
            agent_name: Agent 名称（如 LogAgent）

        Returns:
            str: 节点名称（如 log_agent_node）
        """
        # 常用专家节点走固定映射，保证图节点名稳定，便于前端和测试引用。
        predefined = {
            "LogAgent": "log_agent_node",
            "DomainAgent": "domain_agent_node",
            "CodeAgent": "code_agent_node",
            "DatabaseAgent": "database_agent_node",
            "MetricsAgent": "metrics_agent_node",
            "ChangeAgent": "change_agent_node",
            "RunbookAgent": "runbook_agent_node",
            "RuleSuggestionAgent": "rule_suggestion_agent_node",
            "CriticAgent": "critic_agent_node",
            "RebuttalAgent": "rebuttal_agent_node",
            "JudgeAgent": "judge_agent_node",
            "VerificationAgent": "verification_agent_node",
        }
        if agent_name in predefined:
            return predefined[agent_name]
        # 其他扩展 Agent 统一做驼峰 -> 蛇形命名转换，再追加统一后缀。
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", str(agent_name or "").strip()).lower()
        return f"{snake}{self.NODE_AGENT_SUFFIX}"

    def get_route_table(self, agent_specs: List[AgentSpec]) -> Dict[str, str]:
        """
        获取完整的路由表

        路由表用于条件路由，包含所有可能的下一个节点。

        Args:
            agent_specs: AgentSpec 列表

        Returns:
            Dict[str, str]: 路由表映射
        """
        route_table: Dict[str, str] = {
            self.NODE_ROUND_EVALUATE: self.NODE_ROUND_EVALUATE,
            self.NODE_FINALIZE: self.NODE_FINALIZE,
            self.NODE_ANALYSIS_PARALLEL: self.NODE_ANALYSIS_PARALLEL,
        }

        if bool(getattr(self._orchestrator, "_enable_collaboration", False)):
            route_table[self.NODE_ANALYSIS_COLLABORATION] = self.NODE_ANALYSIS_COLLABORATION

        for spec in agent_specs:
            node_name = self._agent_to_node_name(spec.name)
            route_table[node_name] = node_name

        return route_table

    def compile_graph(
        self,
        agent_specs: List[AgentSpec],
        checkpointer: Optional[Any] = None,
    ):
        """
        构建并编译 LangGraph 图

        编译后的图可以被执行，支持检查点持久化。

        Args:
            agent_specs: AgentSpec 列表
            checkpointer: 可选的检查点保存器，如果未提供则使用配置创建

        Returns:
            CompiledGraph: 编译后的 LangGraph 应用
        """
        if checkpointer is None:
            checkpointer = create_checkpointer(settings)

        graph = self.build(agent_specs)
        compiled = graph.compile(checkpointer=checkpointer)

        logger.info(
            "graph_compiled",
            session_id=self._orchestrator.session_id,
            checkpointer_type=type(checkpointer).__name__,
        )

        return compiled


__all__ = [
    "GraphBuilder",
]
