"""Unit tests for langgraph message ops helpers."""

from langchain_core.messages import AIMessage

from app.runtime.langgraph.message_ops import (
    dedupe_new_messages,
    merge_round_and_message_cards,
    messages_to_cards,
)
from app.runtime.messages import AgentEvidence


def _card(agent: str, conclusion: str) -> AgentEvidence:
    return AgentEvidence(
        agent_name=agent,
        phase="analysis",
        summary=conclusion,
        conclusion=conclusion,
        evidence_chain=[],
        confidence=0.6,
        raw_output={},
    )


def test_dedupe_new_messages_uses_signature():
    existing = [AIMessage(content="same", name="LogAgent")]
    incoming = [AIMessage(content="same", name="LogAgent")]
    assert dedupe_new_messages(existing, incoming) == []


def test_messages_to_cards_extracts_agent_metadata():
    cards = messages_to_cards(
        [
            AIMessage(
                content="发现连接池耗尽",
                name="CodeAgent",
                additional_kwargs={
                    "agent_name": "CodeAgent",
                    "phase": "analysis",
                    "conclusion": "连接池耗尽",
                    "confidence": 0.8,
                },
            )
        ]
    )
    assert len(cards) == 1
    assert cards[0].agent_name == "CodeAgent"
    assert "连接池耗尽" in cards[0].conclusion


def test_merge_round_and_message_cards_dedupes_by_agent_and_conclusion():
    merged = merge_round_and_message_cards(
        [_card("LogAgent", "线程池阻塞")],
        [_card("LogAgent", "线程池阻塞"), _card("CodeAgent", "连接池泄漏")],
        limit=20,
    )
    assert len(merged) == 2
    assert any(c.agent_name == "CodeAgent" for c in merged)
