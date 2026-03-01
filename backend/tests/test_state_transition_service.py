from app.runtime.langgraph.services.state_transition_service import StateTransitionService
from app.runtime.messages import AgentEvidence


class DummyMsg:
    def __init__(self, content: str, name: str):
        self.content = content
        self.name = name
        self.additional_kwargs = {"phase": "analysis", "confidence": 0.7}


def test_state_transition_projects_history_from_messages():
    service = StateTransitionService(
        dedupe_new_messages=lambda existing, new: list(new),
        message_deltas_from_cards=lambda cards: [DummyMsg(c.conclusion, c.agent_name) for c in cards],
        derive_conversation_state=lambda history_cards, **kwargs: {
            "claims": [{"agent": c.agent_name, "conclusion": c.conclusion} for c in history_cards],
            "open_questions": [],
            "agent_outputs": {},
        },
        messages_to_cards=lambda messages: [
            AgentEvidence(
                agent_name=getattr(m, "name", "unknown"),
                phase="analysis",
                summary=str(getattr(m, "content", "")),
                conclusion=str(getattr(m, "content", "")),
                evidence_chain=[],
                confidence=0.6,
                raw_output={},
            )
            for m in messages
        ],
        merge_round_and_message_cards=lambda round_cards, message_cards: list(round_cards) + [
            c for c in message_cards if c.conclusion not in {x.conclusion for x in round_cards}
        ],
        structured_snapshot=lambda merged: {
            "phase_state": {
                "current_round": int(merged.get("current_round") or 1),
                "executed_rounds": int(merged.get("executed_rounds") or 0),
                "consensus_reached": bool(merged.get("consensus_reached") or False),
                "continue_next_round": bool(merged.get("continue_next_round") or False),
            },
            "routing_state": {
                "next_step": str(merged.get("next_step") or ""),
                "agent_commands": dict(merged.get("agent_commands") or {}),
                "discussion_step_count": int(merged.get("discussion_step_count") or 0),
                "max_discussion_steps": int(merged.get("max_discussion_steps") or 0),
                "round_start_turn_index": int(merged.get("round_start_turn_index") or 0),
                "agent_mailbox": dict(merged.get("agent_mailbox") or {}),
                "supervisor_stop_requested": bool(merged.get("supervisor_stop_requested") or False),
                "supervisor_stop_reason": str(merged.get("supervisor_stop_reason") or ""),
                "supervisor_notes": list(merged.get("supervisor_notes") or []),
            },
            "output_state": {
                "history_cards": list(merged.get("history_cards") or []),
                "agent_outputs": dict(merged.get("agent_outputs") or {}),
                "evidence_chain": list(merged.get("evidence_chain") or []),
                "claims": list(merged.get("claims") or []),
                "open_questions": list(merged.get("open_questions") or []),
                "final_payload": dict(merged.get("final_payload") or {}),
            },
        },
    )

    state = {
        "messages": [DummyMsg("old", "LogAgent")],
        "history_cards": [],
        "discussion_step_count": 0,
        "agent_outputs": {},
    }
    result = {
        "messages": [DummyMsg("new", "DomainAgent")],
    }

    next_state = service.apply_step_result(state, result)
    assert next_state["discussion_step_count"] >= 1
    assert len(next_state.get("history_cards") or []) >= 1
    assert next_state["history_cards"][-1].agent_name == "DomainAgent"
