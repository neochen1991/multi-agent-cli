"""Agent and phase node factories.

These nodes execute graph steps directly instead of delegating to wrapper methods
on the orchestrator. The orchestrator still owns low-level LLM/event/storage
helpers, but node-level state transitions are now defined here.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from app.runtime.langgraph.execution import call_agent


def _apply_step_result(orchestrator: Any, state: Dict[str, Any], result: Dict[str, Any] | None) -> Dict[str, Any]:
    return orchestrator._graph_apply_step_result(state, result)


async def execute_single_phase_agent(
    orchestrator: Any,
    *,
    agent_name: str,
    loop_round: int,
    compact_context: Dict[str, Any],
    history_cards: list[Any],
    agent_commands: Dict[str, Dict[str, Any]] | None = None,
    dialogue_items: list[Dict[str, Any]] | None = None,
) -> None:
    spec = orchestrator._spec_by_name(agent_name)
    if not spec:
        return
    round_number = len(orchestrator.turns) + 1
    assigned_command = (agent_commands or {}).get(agent_name)
    if assigned_command:
        await orchestrator._emit_agent_command_issued(
            commander="ProblemAnalysisAgent",
            target=agent_name,
            loop_round=loop_round,
            round_number=round_number,
            command=assigned_command,
        )
    prompt = orchestrator._build_peer_driven_prompt(
        spec=spec,
        loop_round=loop_round,
        context=compact_context,
        history_cards=history_cards,
        assigned_command=assigned_command,
        dialogue_items=dialogue_items,
    )
    try:
        turn = await call_agent(
            orchestrator,
            spec=spec,
            prompt=prompt,
            round_number=round_number,
            loop_round=loop_round,
            history_cards_context=history_cards,
        )
    except Exception as exc:  # pragma: no cover - delegated fallback path
        error_text = str(exc).strip() or exc.__class__.__name__
        turn = await orchestrator._create_fallback_turn(
            spec=spec,
            prompt=prompt,
            round_number=round_number,
            loop_round=loop_round,
            error_text=error_text,
        )
    await orchestrator._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
    if assigned_command:
        await orchestrator._emit_agent_command_feedback(
            source=agent_name,
            loop_round=loop_round,
            round_number=round_number,
            command=assigned_command,
            turn=turn,
        )


def build_agent_node(orchestrator: Any, agent_name: str) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        dialogue_items = orchestrator._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=6,
            char_budget=720,
        )
        compact_context = orchestrator._compact_round_context(context_summary)
        await execute_single_phase_agent(
            orchestrator,
            agent_name=agent_name,
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
        )
        if agent_name == "JudgeAgent":
            await orchestrator._emit_problem_analysis_final_summary(
                loop_round=loop_round,
                history_cards=history_cards,
            )
        return _apply_step_result(orchestrator, state, {"history_cards": history_cards})

    return _node


def build_phase_handler_node(
    orchestrator: Any,
    handler_name: str,
) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        handler = getattr(orchestrator, handler_name)
        result = await handler(state)
        return _apply_step_result(orchestrator, state, result)

    return _node
