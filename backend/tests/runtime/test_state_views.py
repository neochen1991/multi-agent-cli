"""State/message projection tests."""

from langchain_core.messages import AIMessage

from app.runtime.langgraph.state_views import (
    dialogue_items_from_messages,
    history_cards_for_state,
    round_cards_for_routing,
)
from app.runtime.messages import AgentEvidence


def test_history_cards_for_state_merges_stored_cards_with_message_projection():
    stored = [
        AgentEvidence(
            agent_name="ProblemAnalysisAgent",
            phase="coordination",
            summary="主控拆解",
            conclusion="先看日志和数据库",
            evidence_chain=[],
            confidence=0.61,
            raw_output={},
        )
    ]
    state = {
        "history_cards": stored,
        "messages": [
            AIMessage(
                content="我确认连接池耗尽是关键线索",
                name="LogAgent",
                additional_kwargs={
                    "agent_name": "LogAgent",
                    "phase": "analysis",
                    "conclusion": "连接池耗尽",
                    "confidence": 0.78,
                },
            )
        ],
    }

    cards = history_cards_for_state(state, limit=20)

    assert [card.agent_name for card in cards] == ["ProblemAnalysisAgent", "LogAgent"]


def test_round_cards_for_routing_prefers_current_round_slice_plus_messages():
    history_cards = [
        AgentEvidence(
            agent_name="ProblemAnalysisAgent",
            phase="coordination",
            summary="主控拆解",
            conclusion="派发日志与代码调查",
            evidence_chain=[],
            confidence=0.55,
            raw_output={},
        ),
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码闭包",
            conclusion="事务持锁过长",
            evidence_chain=[],
            confidence=0.66,
            raw_output={},
        ),
    ]
    state = {
        "history_cards": history_cards,
        "round_start_turn_index": 1,
        "messages": [
            AIMessage(
                content="我确认连接池耗尽是关键线索",
                name="LogAgent",
                additional_kwargs={
                    "agent_name": "LogAgent",
                    "phase": "analysis",
                    "conclusion": "连接池耗尽",
                    "confidence": 0.78,
                },
            )
        ],
    }

    cards = round_cards_for_routing(state)

    assert [card.agent_name for card in cards] == ["CodeAgent", "LogAgent"]


def test_dialogue_items_from_messages_dedupes_same_speaker_repeats_and_respects_budget():
    messages = [
        AIMessage(
            content="订单接口 502，先看数据库连接池。",
            name="ProblemAnalysisAgent",
            additional_kwargs={"agent_name": "ProblemAnalysisAgent", "phase": "coordination"},
        ),
        AIMessage(
            content="订单接口 502，先看数据库连接池。",
            name="ProblemAnalysisAgent",
            additional_kwargs={"agent_name": "ProblemAnalysisAgent", "phase": "coordination"},
        ),
        AIMessage(
            content="我看到 HikariPool 在 30s 后超时，随后网关返回 502。",
            name="LogAgent",
            additional_kwargs={
                "agent_name": "LogAgent",
                "phase": "analysis",
                "conclusion": "连接池耗尽",
            },
        ),
    ]

    items = dialogue_items_from_messages(messages, limit=8, char_budget=300)

    assert len(items) == 2
    assert items[0]["speaker"] == "ProblemAnalysisAgent"
    assert items[1]["speaker"] == "LogAgent"
    assert items[1]["conclusion"] == "连接池耗尽"
