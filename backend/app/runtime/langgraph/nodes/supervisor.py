"""Supervisor node execution for LangGraph debate runtime."""

from __future__ import annotations

from typing import Any, Dict

from app.runtime.langgraph.mailbox import clone_mailbox, compact_mailbox, enqueue_message
from app.runtime.langgraph.state import structured_state_snapshot
from app.runtime.messages import AgentMessage


async def execute_supervisor_decide(orchestrator: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    history_cards = list(state.get("history_cards") or [])
    dialogue_items = orchestrator._dialogue_items_from_messages(
        list(state.get("messages") or []),
        limit=6,
        char_budget=720,
    )
    loop_round = int(state.get("current_round") or 1)
    discussion_step_count = int(state.get("discussion_step_count") or 0)
    max_discussion_steps = int(state.get("max_discussion_steps") or orchestrator.MAX_DISCUSSION_STEPS_PER_ROUND)
    round_cards = orchestrator._round_cards_for_routing(state)
    preseed_step = str(state.get("next_step") or "").strip()
    supervisor_stop_requested = bool(state.get("supervisor_stop_requested") or False)
    supervisor_stop_reason = str(state.get("supervisor_stop_reason") or "").strip()

    routing_result = await orchestrator._routing_strategy.decide(
        orchestrator=orchestrator,
        state=state,
        history_cards=history_cards,
        round_cards=round_cards,
        dialogue_items=dialogue_items,
        loop_round=loop_round,
        discussion_step_count=discussion_step_count,
        max_discussion_steps=max_discussion_steps,
        preseed_step=preseed_step,
        supervisor_stop_requested=supervisor_stop_requested,
        supervisor_stop_reason=supervisor_stop_reason,
    )
    route_decision = dict(routing_result.decision or {})
    mode = str(routing_result.mode or "langgraph_supervisor_dynamic")

    convo_state = orchestrator._derive_conversation_state_with_context(
        history_cards,
        messages=list(state.get("messages") or []),
        existing_agent_outputs=dict(state.get("agent_outputs") or {}),
    )
    next_step = str(route_decision.get("next_step") or "").strip()
    note = {
        "loop_round": loop_round,
        "discussion_step_count": discussion_step_count,
        "max_discussion_steps": max_discussion_steps,
        "next_step": next_step,
        "open_questions_count": len(convo_state.get("open_questions") or []),
        "claims_count": len(convo_state.get("claims") or []),
        "reason": str(route_decision.get("reason") or ""),
        "should_stop": bool(route_decision.get("should_stop") or False),
        "stop_reason": str(route_decision.get("stop_reason") or ""),
    }
    await orchestrator._emit_event(
        {
            "type": "supervisor_decision",
            "session_id": orchestrator.session_id,
            "loop_round": loop_round,
            "discussion_step_count": discussion_step_count,
            "max_discussion_steps": max_discussion_steps,
            "next_step": next_step or None,
            "reason": str(route_decision.get("reason") or ""),
            "mode": mode,
            "should_stop": bool(route_decision.get("should_stop") or False),
            "stop_reason": str(route_decision.get("stop_reason") or "")[:240],
            "open_questions_count": note["open_questions_count"],
            "claims_count": note["claims_count"],
        }
    )
    notes = list(state.get("supervisor_notes") or [])
    notes.append(note)
    result: Dict[str, Any] = {
        "history_cards": history_cards,
        "next_step": next_step,
        "supervisor_stop_requested": bool(route_decision.get("should_stop") or False),
        "supervisor_stop_reason": str(route_decision.get("stop_reason") or ""),
        "supervisor_notes": notes[-20:],
        **convo_state,
    }
    mailbox = clone_mailbox(state.get("agent_mailbox") or {})
    if "agent_commands" in route_decision:
        commands = dict(route_decision.get("agent_commands") or {})
        result["agent_commands"] = commands
        for target, command in commands.items():
            if not isinstance(command, dict):
                continue
            enqueue_message(
                mailbox,
                receiver=target,
                message=AgentMessage(
                    sender="ProblemAnalysisAgent",
                    receiver=str(target),
                    message_type="command",
                    content={
                        "task": str(command.get("task") or "").strip(),
                        "focus": str(command.get("focus") or "").strip(),
                        "expected_output": str(command.get("expected_output") or "").strip(),
                    },
                ),
            )
    result["agent_mailbox"] = compact_mailbox(mailbox)
    merged_preview = {**dict(state), **result}
    return {**result, **structured_state_snapshot(merged_preview)}
