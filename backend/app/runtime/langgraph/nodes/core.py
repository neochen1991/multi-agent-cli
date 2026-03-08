"""
核心节点工厂模块。

这个文件只负责把 orchestrator 的方法包装成 LangGraph 可挂载节点，
不在这里承载业务判断。这样图构建层和运行时逻辑可以保持解耦。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from app.runtime.langgraph.nodes.supervisor import execute_supervisor_decide


def build_init_session_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """构建会话初始化节点。"""
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        """把执行权转交给 orchestrator 的 `_graph_init_session`。"""
        return await orchestrator._graph_init_session(state)

    return _node


def build_round_start_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """构建新一轮分析启动节点。"""
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        """把执行权转交给 orchestrator 的 `_graph_round_start`。"""
        return await orchestrator._graph_round_start(state)

    return _node


def build_supervisor_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """构建 Supervisor 决策节点。"""
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 supervisor 决策并返回下一步图状态增量。"""
        return await execute_supervisor_decide(orchestrator, state)

    return _node


def build_round_evaluate_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """构建轮次评估节点。"""
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        """把执行权转交给 orchestrator 的 `_graph_round_evaluate`。"""
        return await orchestrator._graph_round_evaluate(state)

    return _node


def build_finalize_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """构建最终收尾节点。"""
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        """把执行权转交给 orchestrator 的 `_graph_finalize`。"""
        return await orchestrator._graph_finalize(state)

    return _node
