"""Agent and phase node factories.

These nodes execute graph steps directly instead of delegating to wrapper methods
on the orchestrator. The orchestrator still owns low-level LLM/event/storage
helpers, but node-level state transitions are now defined here.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from app.runtime.langgraph.mailbox import clone_mailbox, compact_mailbox, dequeue_messages, enqueue_message
from app.runtime.messages import AgentMessage


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
    inbox_messages: list[Dict[str, Any]] | None = None,
    agent_mailbox: Dict[str, list[Dict[str, Any]]] | None = None,
) -> Dict[str, Any]:
    spec = orchestrator._spec_by_name(agent_name)
    if not spec:
        return {"agent_mailbox": compact_mailbox(clone_mailbox(agent_mailbox or {}))}
    round_number = len(orchestrator.turns) + 1
    mailbox = clone_mailbox(agent_mailbox or {})
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
        inbox_messages=inbox_messages,
    )
    turn = await orchestrator._agent_runner.run_agent(
        spec=spec,
        prompt=prompt,
        round_number=round_number,
        loop_round=loop_round,
        history_cards_context=history_cards,
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
        enqueue_message(
            mailbox,
            receiver="ProblemAnalysisAgent",
            message=AgentMessage(
                sender=agent_name,
                receiver="ProblemAnalysisAgent",
                message_type="feedback",
                content={
                    "command": str(assigned_command.get("task") or "")[:240],
                    "conclusion": str((turn.output_content or {}).get("conclusion") or "")[:240],
                    "confidence": float(turn.confidence or 0.0),
                },
            ),
        )
    conclusion = str((turn.output_content or {}).get("conclusion") or "")[:280]
    evidence = list((turn.output_content or {}).get("evidence_chain") or [])[:3]
    for receiver in ["ProblemAnalysisAgent", *list(orchestrator.PARALLEL_ANALYSIS_AGENTS)]:
        if receiver == agent_name:
            continue
        enqueue_message(
            mailbox,
            receiver=receiver,
            message=AgentMessage(
                sender=agent_name,
                receiver=receiver,
                message_type="evidence",
                content={
                    "phase": turn.phase,
                    "conclusion": conclusion,
                    "evidence_chain": evidence,
                    "confidence": float(turn.confidence or 0.0),
                },
            ),
        )
    return {"agent_mailbox": compact_mailbox(mailbox)}


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
        mailbox = clone_mailbox(state.get("agent_mailbox") or {})
        inbox_messages, mailbox = dequeue_messages(mailbox, receiver=agent_name)
        compact_context = orchestrator._compact_round_context(context_summary)
        execution_result = await execute_single_phase_agent(
            orchestrator,
            agent_name=agent_name,
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
            agent_mailbox=mailbox,
        )
        mailbox = clone_mailbox(execution_result.get("agent_mailbox") or mailbox)
        if agent_name == "JudgeAgent":
            await orchestrator._emit_problem_analysis_final_summary(
                loop_round=loop_round,
                history_cards=history_cards,
            )
        result: Dict[str, Any] = {
            "history_cards": history_cards,
            "agent_mailbox": compact_mailbox(mailbox),
        }
        if history_cards:
            latest_message = orchestrator._card_to_ai_message(history_cards[-1])
            if latest_message is not None:
                result["messages"] = [latest_message]
        return _apply_step_result(orchestrator, state, result)

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
