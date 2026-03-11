"""test邮箱flow相关测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.runtime.langgraph.mailbox import clone_mailbox, dequeue_messages, enqueue_message
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.langgraph.state import DebateTurn
from app.runtime.messages import AgentMessage


def test_mailbox_enqueue_and_dequeue_roundtrip():
    """验证邮箱enqueueanddequeue往返。"""
    
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
    """验证轮次startenqueues主Agentcommandsto邮箱。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    orchestrator._emit_event = AsyncMock()

    async def _fake_commander(**kwargs):
        """为测试场景提供主Agent模拟实现。"""
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


def test_evidence_recipients_prefers_relevant_gap_owners():
    """证据消息应优先发给与当前缺口最相关的专家，而不是默认全员广播。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    turn = DebateTurn(
        round_number=1,
        phase="analysis",
        agent_name="LogAgent",
        agent_role="日志分析专家",
        model={"name": "test"},
        input_message="x",
        output_content={
            "chat_message": "日志显示数据库锁等待先升高，代码侧需要核对事务边界。",
            "conclusion": "数据库锁等待放大了连接池耗尽，需要数据库与代码双侧继续补证。",
            "confidence": 0.82,
            "evidence_chain": ["top sql 显示 lock wait 增长", "trace 显示事务持有连接时间过长"],
            "next_checks": ["请代码侧核对事务边界", "请数据库侧确认锁等待链路"],
        },
        confidence=0.82,
        started_at=None,
        completed_at=None,
    )

    recipients = orchestrator._evidence_recipients(
        sender="LogAgent",
        turn=turn,
        assigned_command={"followup_gaps": ["数据库锁等待是否先发生"]},
        context_with_tools={"focused_context": {"causal_summary": "数据库锁等待与长事务同时出现"}},
    )

    assert "ProblemAnalysisAgent" in recipients
    assert "DatabaseAgent" in recipients
    assert "CodeAgent" in recipients
    assert "LogAgent" not in recipients
