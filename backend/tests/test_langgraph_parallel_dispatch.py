"""Tests for LangGraph parallel dispatch helpers."""

from __future__ import annotations

from langgraph.types import Send

from app.runtime.langgraph.nodes.agent_subgraph import build_parallel_route_function


def test_analysis_parallel_returns_send_objects() -> None:
    router = build_parallel_route_function(
        orchestrator=object(),
        parallel_agents=["LogAgent", "CodeAgent", "DomainAgent"],
    )
    state = {
        "next_step": "analysis_parallel",
        "agent_commands": {"LogAgent": {"focus": "timeout"}, "CodeAgent": {"focus": "pool"}},
        "messages": [],
        "context_summary": {"service": "order-service"},
        "current_round": 1,
        "agent_mailbox": {},
        "history_cards": [],
    }

    sends = router(state)
    assert isinstance(sends, list)
    assert len(sends) == 2
    assert all(isinstance(item, Send) for item in sends)
    assert [item.node for item in sends] == ["log_agent_node", "code_agent_node"]
    assert sends[0].arg.get("agent_name") == "LogAgent"
    assert sends[1].arg.get("agent_name") == "CodeAgent"


def test_parallel_route_fallback_uses_default_agents() -> None:
    router = build_parallel_route_function(
        orchestrator=object(),
        parallel_agents=["LogAgent", "CodeAgent"],
    )
    state = {"next_step": "analysis_parallel", "agent_commands": {}}

    sends = router(state)
    assert isinstance(sends, list)
    assert len(sends) == 2
    assert [item.node for item in sends] == ["log_agent_node", "code_agent_node"]

