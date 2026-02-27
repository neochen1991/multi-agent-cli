"""Tests for explicit mailbox-based agent communication."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.runtime.langgraph.mailbox import clone_mailbox, dequeue_messages, enqueue_message
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.messages import AgentMessage


def test_mailbox_enqueue_and_dequeue_roundtrip():
    mailbox = {}
    enqueue_message(
        mailbox,
        receiver="LogAgent",
        message=AgentMessage(
            sender="ProblemAnalysisAgent",
            receiver="LogAgent",
            message_type="command",
            content={"task": "analyze logs"},
        ),
    )
    copied = clone_mailbox(mailbox)
    items, rest = dequeue_messages(copied, receiver="LogAgent")

    assert len(items) == 1
    assert items[0]["sender"] == "ProblemAnalysisAgent"
    assert items[0]["message_type"] == "command"
    assert "LogAgent" not in rest


@pytest.mark.asyncio
async def test_round_start_enqueues_commander_commands_to_mailbox(monkeypatch):
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    orchestrator._emit_event = AsyncMock()

    async def _fake_commander(**kwargs):
        _ = kwargs
        return {
            "commands": {
                "LogAgent": {
                    "target_agent": "LogAgent",
                    "task": "分析502与CPU异常",
                    "focus": "线程池与连接池",
                    "expected_output": "证据链+结论",
                }
            },
            "next_mode": "single",
            "next_agent": "LogAgent",
            "should_stop": False,
            "stop_reason": "",
        }

    monkeypatch.setattr(orchestrator, "_run_problem_analysis_commander", _fake_commander)
    monkeypatch.setattr(
        orchestrator,
        "_route_from_commander_output",
        lambda **kwargs: {"next_step": "speak:LogAgent", "should_stop": False, "stop_reason": ""},
    )

    state = {
        "current_round": 0,
        "context_summary": {},
        "history_cards": [],
        "messages": [],
        "agent_outputs": {},
        "agent_mailbox": {},
    }
    result = await orchestrator._graph_round_start(state)

    inbox = result["agent_mailbox"]["LogAgent"]
    assert len(inbox) >= 1
    assert inbox[-1]["sender"] == "ProblemAnalysisAgent"
    assert inbox[-1]["message_type"] == "command"
    assert "分析502与CPU异常" in str(inbox[-1]["content"].get("task", ""))

