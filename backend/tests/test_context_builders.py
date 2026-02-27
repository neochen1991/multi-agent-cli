"""Unit tests for langgraph context builder helpers."""

from app.runtime.langgraph.context_builders import (
    collect_peer_items_from_cards,
    collect_peer_items_from_dialogue,
    coordination_peer_items,
)
from app.runtime.messages import AgentEvidence


def _card(agent: str, conclusion: str, confidence: float = 0.7) -> AgentEvidence:
    return AgentEvidence(
        agent_name=agent,
        phase="analysis",
        summary=f"{agent} summary",
        conclusion=conclusion,
        evidence_chain=[],
        confidence=confidence,
        raw_output={},
    )


def test_collect_peer_items_from_dialogue_filters_self_and_dedup():
    items = collect_peer_items_from_dialogue(
        [
            {"speaker": "CodeAgent", "message": "m1", "conclusion": "c1", "phase": "analysis"},
            {"speaker": "CodeAgent", "message": "m2", "conclusion": "c2", "phase": "analysis"},
            {"speaker": "LogAgent", "message": "m3", "conclusion": "c3", "phase": "analysis"},
        ],
        exclude_agent="CodeAgent",
        limit=5,
    )

    assert len(items) == 1
    assert items[0]["agent"] == "LogAgent"


def test_collect_peer_items_from_cards_respects_limit():
    cards = [
        _card("LogAgent", "l"),
        _card("CodeAgent", "c"),
        _card("DomainAgent", "d"),
    ]
    items = collect_peer_items_from_cards(cards, exclude_agent="CodeAgent", limit=2)
    assert len(items) == 2
    assert all(item["agent"] != "CodeAgent" for item in items)


def test_coordination_peer_items_falls_back_to_agent_outputs():
    items = coordination_peer_items(
        history_cards=[],
        dialogue_items=[],
        existing_agent_outputs={
            "LogAgent": {"conclusion": "线程池阻塞", "confidence": 0.8},
            "ProblemAnalysisAgent": {"conclusion": "should be excluded"},
        },
        limit=3,
    )
    assert any(item["agent"] == "LogAgent" for item in items)
    assert all(item["agent"] != "ProblemAnalysisAgent" for item in items)
