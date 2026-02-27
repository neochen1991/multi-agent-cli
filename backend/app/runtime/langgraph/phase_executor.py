"""Phase execution service for multi-agent parallel/collaboration waves."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.runtime.langgraph.mailbox import compact_mailbox, dequeue_messages, enqueue_message
from app.runtime.langgraph.state import AgentSpec
from app.runtime.messages import AgentEvidence, AgentMessage

logger = structlog.get_logger()


class PhaseExecutor:
    """Run heavy phase-level execution while keeping orchestrator lightweight."""

    def __init__(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    async def run_parallel_analysis_phase(
        self,
        *,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        agent_commands: Optional[Dict[str, Dict[str, Any]]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        agent_mailbox: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        orchestrator = self._orchestrator
        analysis_specs = {spec.name: spec for spec in orchestrator._agent_sequence() if spec.phase == "analysis"}
        if not analysis_specs:
            return
        commanded_targets = [name for name in dict(agent_commands or {}).keys() if name in analysis_specs]
        target_names = commanded_targets or [name for name in orchestrator.PARALLEL_ANALYSIS_AGENTS if name in analysis_specs]
        parallel_specs = [analysis_specs[name] for name in target_names]
        if not parallel_specs:
            return
        mailbox = agent_mailbox if agent_mailbox is not None else {}
        round_cursor = len(orchestrator.turns) + 1
        parallel_history = list(history_cards)
        round_plans: List[tuple[AgentSpec, int, Dict[str, Any], List[Dict[str, Any]]]] = []
        for spec in parallel_specs:
            round_number = round_cursor
            round_cursor += 1
            inbox_messages, mailbox = dequeue_messages(mailbox, receiver=spec.name)
            assigned_command = (agent_commands or {}).get(spec.name)
            round_plans.append((spec, round_number, assigned_command or {}, inbox_messages))

        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_started",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "agents": [spec.name for spec, _, _, _ in round_plans],
            }
        )
        for spec, round_number, assigned_command, _ in round_plans:
            if assigned_command:
                await orchestrator._emit_agent_command_issued(
                    commander="ProblemAnalysisAgent",
                    target=spec.name,
                    loop_round=loop_round,
                    round_number=round_number,
                    command=assigned_command,
                )

        parallel_inputs: List[tuple[AgentSpec, int, str, Dict[str, Any], List[Dict[str, Any]]]] = []
        for spec, round_number, assigned_command, inbox_messages in round_plans:
            context_with_tools = await orchestrator._build_agent_context_with_tools(
                agent_name=spec.name,
                compact_context=compact_context,
                loop_round=loop_round,
                round_number=round_number,
                assigned_command=assigned_command,
            )
            effective_spec = orchestrator._apply_tool_switch_to_spec(
                spec=spec,
                context_with_tools=context_with_tools,
            )
            prompt = orchestrator._build_agent_prompt(
                spec=effective_spec,
                loop_round=loop_round,
                context=context_with_tools,
                history_cards=parallel_history,
                assigned_command=assigned_command,
                dialogue_items=dialogue_items,
                inbox_messages=inbox_messages,
            )
            parallel_inputs.append((effective_spec, round_number, prompt, assigned_command, inbox_messages))

        parallel_start_time = datetime.utcnow()
        logger.info(
            "parallel_analysis_executing",
            session_id=orchestrator.session_id,
            loop_round=loop_round,
            agents=[spec.name for spec, _, _, _, _ in parallel_inputs],
        )

        parallel_tasks = [
            asyncio.create_task(
                orchestrator._agent_runner.run_agent(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    history_cards_context=history_cards,
                )
            )
            for spec, round_number, prompt, _, _ in parallel_inputs
        ]
        parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

        parallel_duration = (datetime.utcnow() - parallel_start_time).total_seconds()
        logger.info(
            "parallel_analysis_completed_duration",
            session_id=orchestrator.session_id,
            loop_round=loop_round,
            duration_seconds=parallel_duration,
            agents_count=len(parallel_inputs),
        )

        success_count = 0
        error_count = 0
        for (spec, round_number, prompt, assigned_command, _), result in zip(parallel_inputs, parallel_results):
            if isinstance(result, Exception):
                error_count += 1
                error_text = str(result).strip() or result.__class__.__name__
                logger.error(
                    "parallel_agent_failed",
                    session_id=orchestrator.session_id,
                    agent=spec.name,
                    loop_round=loop_round,
                    error=error_text,
                )
                turn = await orchestrator._create_fallback_turn(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    error_text=error_text,
                )
            else:
                success_count += 1
                turn = result
            await orchestrator._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
            if assigned_command:
                await orchestrator._emit_agent_command_feedback(
                    source=spec.name,
                    loop_round=loop_round,
                    round_number=round_number,
                    command=assigned_command,
                    turn=turn,
                )
                enqueue_message(
                    mailbox,
                    receiver="ProblemAnalysisAgent",
                    message=AgentMessage(
                        sender=spec.name,
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
            for receiver in ["ProblemAnalysisAgent", *target_names]:
                if receiver == spec.name:
                    continue
                enqueue_message(
                    mailbox,
                    receiver=receiver,
                    message=AgentMessage(
                        sender=spec.name,
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

        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_completed",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "agents": [spec.name for spec, _, _, _, _ in parallel_inputs],
                "success_count": success_count,
                "error_count": error_count,
                "duration_seconds": parallel_duration,
            }
        )
        if agent_mailbox is not None:
            agent_mailbox.clear()
            agent_mailbox.update(compact_mailbox(mailbox))

    async def run_collaboration_phase(
        self,
        *,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        agent_mailbox: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        orchestrator = self._orchestrator
        parallel_specs = [
            spec
            for spec in orchestrator._agent_sequence()
            if spec.phase == "analysis" and spec.name in set(orchestrator.PARALLEL_ANALYSIS_AGENTS)
        ]
        if not parallel_specs:
            return
        mailbox = agent_mailbox if agent_mailbox is not None else {}
        peer_cards = orchestrator._latest_cards_for_agents(
            history_cards=history_cards,
            agent_names=[spec.name for spec in parallel_specs],
            limit=orchestrator.COLLABORATION_PEER_LIMIT,
        )
        round_cursor = len(orchestrator.turns) + 1
        collab_inputs: List[tuple[AgentSpec, int, str, List[Dict[str, Any]]]] = []
        for spec in parallel_specs:
            round_number = round_cursor
            round_cursor += 1
            inbox_messages, mailbox = dequeue_messages(mailbox, receiver=spec.name)
            context_with_tools = await orchestrator._build_agent_context_with_tools(
                agent_name=spec.name,
                compact_context=compact_context,
                loop_round=loop_round,
                round_number=round_number,
                assigned_command=None,
            )
            effective_spec = orchestrator._apply_tool_switch_to_spec(
                spec=spec,
                context_with_tools=context_with_tools,
            )
            prompt = orchestrator._build_collaboration_prompt(
                spec=effective_spec,
                loop_round=loop_round,
                context=context_with_tools,
                peer_cards=peer_cards,
                dialogue_items=dialogue_items,
                inbox_messages=inbox_messages,
            )
            collab_inputs.append((effective_spec, round_number, prompt, inbox_messages))

        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_collaboration_started",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "agents": [spec.name for spec, _, _, _ in collab_inputs],
            }
        )

        collab_start_time = datetime.utcnow()
        logger.info(
            "collaboration_phase_executing",
            session_id=orchestrator.session_id,
            loop_round=loop_round,
            agents=[spec.name for spec, _, _, _ in collab_inputs],
        )

        collab_tasks = [
            asyncio.create_task(
                orchestrator._agent_runner.run_agent(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    history_cards_context=history_cards,
                )
            )
            for spec, round_number, prompt, _ in collab_inputs
        ]
        collab_results = await asyncio.gather(*collab_tasks, return_exceptions=True)

        collab_duration = (datetime.utcnow() - collab_start_time).total_seconds()
        logger.info(
            "collaboration_phase_completed_duration",
            session_id=orchestrator.session_id,
            loop_round=loop_round,
            duration_seconds=collab_duration,
            agents_count=len(collab_inputs),
        )

        success_count = 0
        error_count = 0
        for (spec, round_number, prompt, _), result in zip(collab_inputs, collab_results):
            if isinstance(result, Exception):
                error_count += 1
                error_text = str(result).strip() or result.__class__.__name__
                logger.error(
                    "collaboration_agent_failed",
                    session_id=orchestrator.session_id,
                    agent=spec.name,
                    loop_round=loop_round,
                    error=error_text,
                )
                turn = await orchestrator._create_fallback_turn(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    error_text=error_text,
                )
            else:
                success_count += 1
                turn = result
            await orchestrator._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
            conclusion = str((turn.output_content or {}).get("conclusion") or "")[:280]
            evidence = list((turn.output_content or {}).get("evidence_chain") or [])[:3]
            for receiver in ["ProblemAnalysisAgent", *list(orchestrator.PARALLEL_ANALYSIS_AGENTS)]:
                if receiver == spec.name:
                    continue
                enqueue_message(
                    mailbox,
                    receiver=receiver,
                    message=AgentMessage(
                        sender=spec.name,
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

        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_collaboration_completed",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "agents": [spec.name for spec, _, _, _ in collab_inputs],
                "success_count": success_count,
                "error_count": error_count,
                "duration_seconds": collab_duration,
            }
        )
        if agent_mailbox is not None:
            agent_mailbox.clear()
            agent_mailbox.update(compact_mailbox(mailbox))


__all__ = ["PhaseExecutor"]
