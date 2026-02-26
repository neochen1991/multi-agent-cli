"""Supervisor node execution for LangGraph debate runtime."""

from __future__ import annotations

from typing import Any, Dict

import structlog

logger = structlog.get_logger()


async def execute_supervisor_decide(orchestrator: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    history_cards = list(state.get("history_cards") or [])
    prev_history_count = len(history_cards)
    dialogue_items = orchestrator._dialogue_items_from_messages(
        list(state.get("messages") or []),
        limit=6,
        char_budget=720,
    )
    loop_round = int(state.get("current_round") or 1)
    discussion_step_count = int(state.get("discussion_step_count") or 0)
    max_discussion_steps = int(state.get("max_discussion_steps") or orchestrator.MAX_DISCUSSION_STEPS_PER_ROUND)
    round_cards = orchestrator._round_cards_from_state(state)
    preseed_step = str(state.get("next_step") or "").strip()
    supervisor_stop_requested = bool(state.get("supervisor_stop_requested") or False)
    supervisor_stop_reason = str(state.get("supervisor_stop_reason") or "").strip()

    route_decision: Dict[str, Any]
    mode = "langgraph_supervisor_dynamic"
    if preseed_step and discussion_step_count == 0:
        route_decision = {
            "next_step": preseed_step,
            "should_stop": supervisor_stop_requested,
            "stop_reason": supervisor_stop_reason,
            "reason": "采用主Agent开场拆解后的预置调度",
        }
        mode = "langgraph_supervisor_seeded"
    else:
        recent_judge_card = orchestrator._recent_judge_card(round_cards)
        recent_judge_conf = float(recent_judge_card.confidence or 0.0) if recent_judge_card else 0.0
        if recent_judge_card and recent_judge_conf >= orchestrator.consensus_threshold:
            route_decision = {
                "next_step": "",
                "should_stop": True,
                "stop_reason": "JudgeAgent 已给出高置信裁决",
                "reason": "达到裁决阈值，主Agent结束讨论",
            }
            mode = "langgraph_supervisor_consensus_shortcut"
        elif discussion_step_count >= max_discussion_steps:
            route_decision = orchestrator._fallback_supervisor_route(state=state, round_cards=round_cards)
            route_decision["reason"] = f"达到讨论步数预算({max_discussion_steps})，使用回退调度"
            mode = "langgraph_supervisor_budget_guard"
        else:
            context_summary = state.get("context_summary") or {}
            compact_context = orchestrator._compact_round_context(context_summary)
            round_cards = list(history_cards[-10:])
            try:
                commander_output = await orchestrator._run_problem_analysis_supervisor_router(
                    loop_round=loop_round,
                    compact_context=compact_context,
                    history_cards=history_cards,
                    round_history_cards=round_cards,
                    dialogue_items=dialogue_items,
                    discussion_step_count=discussion_step_count,
                    max_discussion_steps=max_discussion_steps,
                )
                route_decision = orchestrator._route_from_commander_output(
                    payload=commander_output,
                    state=state,
                    round_cards=orchestrator._round_cards_from_state(state),
                )
                merged_commands = dict(state.get("agent_commands") or {})
                merged_commands.update(dict(commander_output.get("commands") or {}))
                route_decision["agent_commands"] = merged_commands
            except Exception as exc:
                logger.warning(
                    "supervisor_dynamic_routing_failed",
                    session_id=orchestrator.session_id,
                    loop_round=loop_round,
                    error=str(exc).strip() or exc.__class__.__name__,
                )
                route_decision = orchestrator._fallback_supervisor_route(state=state, round_cards=round_cards)
                mode = "langgraph_supervisor_fallback"

    route_decision = orchestrator._route_guardrail(
        state=state,
        round_cards=orchestrator._round_cards_from_state(
            {"history_cards": history_cards, "round_start_turn_index": state.get("round_start_turn_index")}
        ),
        route_decision=route_decision,
    )

    convo_state = orchestrator._derive_conversation_state(history_cards)
    message_deltas = orchestrator._message_deltas_from_cards(history_cards[prev_history_count:])
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
    if message_deltas:
        result["messages"] = message_deltas
    if "agent_commands" in route_decision:
        result["agent_commands"] = dict(route_decision.get("agent_commands") or {})
    return result

