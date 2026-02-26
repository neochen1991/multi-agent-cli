"""Core orchestration node factories."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from app.runtime.langgraph.nodes.supervisor import execute_supervisor_decide


def build_init_session_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        return await orchestrator._graph_init_session(state)

    return _node


def build_round_start_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        return await orchestrator._graph_round_start(state)

    return _node


def build_supervisor_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        return await execute_supervisor_decide(orchestrator, state)

    return _node


def build_round_evaluate_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        return await orchestrator._graph_round_evaluate(state)

    return _node


def build_finalize_node(orchestrator: Any) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        return await orchestrator._graph_finalize(state)

    return _node
