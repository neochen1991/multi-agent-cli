"""
LangGraph Runtime orchestration for multi-agent, multi-round debate.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

import structlog
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.core.event_schema import enrich_event
from app.runtime.langgraph.prompts import (
    build_agent_prompt as build_agent_prompt_template,
    build_collaboration_prompt as build_collaboration_prompt_template,
    build_peer_driven_prompt as build_peer_driven_prompt_template,
    build_problem_analysis_commander_prompt as build_problem_analysis_commander_prompt_template,
    build_problem_analysis_supervisor_prompt as build_problem_analysis_supervisor_prompt_template,
    coordinator_command_schema as coordinator_command_schema_template,
    judge_output_schema as judge_output_schema_template,
)
from app.runtime.langgraph.parsers import (
    normalize_agent_output as normalize_agent_output_parser,
    normalize_commander_output as normalize_commander_output_parser,
    normalize_judge_output,
    normalize_normal_output,
)
from app.runtime.langgraph.execution import call_agent as execute_runtime_agent_call
from app.runtime.langgraph.routing import (
    agent_from_step as agent_from_step_route,
    fallback_supervisor_route as fallback_supervisor_route_helper,
    judge_is_ready as judge_is_ready_route,
    recent_agent_card as recent_agent_card_route,
    route_from_commander_output as route_from_commander_output_helper,
    round_agent_counts as round_agent_counts_route,
    route_guardrail as route_guardrail_helper,
    step_for_agent as step_for_agent_route,
    supervisor_step_to_node as supervisor_step_to_node_route,
)
from app.runtime.langgraph.nodes import (
    build_agent_node,
    build_finalize_node,
    build_init_session_node,
    build_phase_handler_node,
    build_round_evaluate_node,
    build_round_start_node,
    build_supervisor_node,
    execute_single_phase_agent,
)
from app.runtime.langgraph.specs import (
    agent_sequence as build_agent_sequence,
    problem_analysis_agent_spec as build_problem_analysis_agent_spec,
)
from app.runtime.langgraph.state import AgentSpec, DebateExecState as _DebateExecState, DebateTurn
from app.runtime.messages import AgentEvidence, FinalVerdict, RoundCheckpoint
from app.runtime.session_store import runtime_session_store

logger = structlog.get_logger()


class LangGraphRuntimeOrchestrator:
    """LangGraph-backed orchestrator with persisted checkpoints."""

    MAX_HISTORY_ITEMS = 2
    PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent")
    COLLABORATION_PEER_LIMIT = 2
    STREAM_CHUNK_SIZE = 160
    STREAM_MAX_CHUNKS = 16
    JUDGE_FALLBACK_SUMMARY = "需要进一步分析"
    MAX_DISCUSSION_STEPS_PER_ROUND = 12
    DIALOGUE_PROMPT_CHAR_BUDGET = 900

    def __init__(self, consensus_threshold: float = 0.85, max_rounds: int = 1):
        self.consensus_threshold = consensus_threshold
        self.max_rounds = max_rounds
        self.min_rounds = 1
        self.session_id: Optional[str] = None
        self.trace_id: str = ""
        self.turns: List[DebateTurn] = []
        self._active_round_commands: Dict[str, Dict[str, Any]] = {}
        self._event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
        self._llm_semaphore = asyncio.Semaphore(max(1, int(settings.LLM_MAX_CONCURRENCY or 1)))
        self._graph_checkpointer = MemorySaver()
        logger.info(
            "langgraph_runtime_orchestrator_initialized",
            model=settings.llm_model,
            base_url=settings.LLM_BASE_URL,
            max_rounds=max_rounds,
            consensus_threshold=consensus_threshold,
        )

    @staticmethod
    def _is_rate_limited_error(error_text: str) -> bool:
        normalized = str(error_text or "").lower()
        return (
            "429" in normalized
            or "toomanyrequests" in normalized
            or "serveroverloaded" in normalized
            or "rate limit" in normalized
        )

    async def execute(
        self,
        context: Dict[str, Any],
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        self.turns = []
        self._active_round_commands = {}
        self._event_callback = event_callback
        self.session_id = f"ags_{uuid4().hex[:20]}"
        self.trace_id = str(context.get("trace_id") or "")
        context_summary = {
            "log_excerpt": str(context.get("log_content") or "")[:1400],
            "parsed_data": context.get("parsed_data") or {},
            "interface_mapping": context.get("interface_mapping") or {},
            "runtime_assets_count": len(context.get("runtime_assets") or []),
            "dev_assets_count": len(context.get("dev_assets") or []),
            "design_assets_count": len(context.get("design_assets") or []),
        }

        graph = StateGraph(_DebateExecState)
        graph.add_node("init_session", build_init_session_node(self))
        graph.add_node("round_start", build_round_start_node(self))
        graph.add_node("supervisor_decide", build_supervisor_node(self))
        graph.add_node("analysis_parallel_node", build_phase_handler_node(self, "_graph_analysis_parallel"))
        graph.add_node(
            "analysis_collaboration_node",
            build_phase_handler_node(self, "_graph_analysis_collaboration"),
        )
        graph.add_node("log_agent_node", build_agent_node(self, "LogAgent"))
        graph.add_node("domain_agent_node", build_agent_node(self, "DomainAgent"))
        graph.add_node("code_agent_node", build_agent_node(self, "CodeAgent"))
        graph.add_node("critic_agent_node", build_agent_node(self, "CriticAgent"))
        graph.add_node("rebuttal_agent_node", build_agent_node(self, "RebuttalAgent"))
        graph.add_node("judge_agent_node", build_agent_node(self, "JudgeAgent"))
        graph.add_node("round_evaluate", build_round_evaluate_node(self))
        graph.add_node("finalize", build_finalize_node(self))
        graph.add_edge(START, "init_session")
        graph.add_edge("init_session", "round_start")
        graph.add_edge("round_start", "supervisor_decide")
        graph.add_conditional_edges(
            "supervisor_decide",
            self._route_after_supervisor_decide,
            {
                "analysis_parallel_node": "analysis_parallel_node",
                "analysis_collaboration_node": "analysis_collaboration_node",
                "log_agent_node": "log_agent_node",
                "domain_agent_node": "domain_agent_node",
                "code_agent_node": "code_agent_node",
                "critic_agent_node": "critic_agent_node",
                "rebuttal_agent_node": "rebuttal_agent_node",
                "judge_agent_node": "judge_agent_node",
                "round_evaluate": "round_evaluate",
            },
        )
        graph.add_edge("analysis_parallel_node", "supervisor_decide")
        graph.add_edge("analysis_collaboration_node", "supervisor_decide")
        graph.add_edge("log_agent_node", "supervisor_decide")
        graph.add_edge("domain_agent_node", "supervisor_decide")
        graph.add_edge("code_agent_node", "supervisor_decide")
        graph.add_edge("critic_agent_node", "supervisor_decide")
        graph.add_edge("rebuttal_agent_node", "supervisor_decide")
        graph.add_edge("judge_agent_node", "supervisor_decide")
        graph.add_conditional_edges(
            "round_evaluate",
            self._route_after_round_evaluate,
            {
                "round_start": "round_start",
                "finalize": "finalize",
            },
        )
        graph.add_edge("finalize", END)
        app = graph.compile(checkpointer=self._graph_checkpointer)

        try:
            result_state = await app.ainvoke(
                {
                    "context": context,
                    "context_summary": context_summary,
                },
                config={"configurable": {"thread_id": str(self.session_id)}},
            )
            return dict(result_state.get("final_payload") or {})
        except Exception:
            if self.session_id:
                await runtime_session_store.fail(self.session_id)
            raise

    async def _graph_init_session(self, state: _DebateExecState) -> _DebateExecState:
        context_summary = state.get("context_summary") or {}
        await runtime_session_store.create(
            session_id=str(self.session_id),
            trace_id=self.trace_id,
            context_summary=context_summary,
        )
        await self._emit_event(
            {
                "type": "session_created",
                "session_id": self.session_id,
                "mode": "langgraph_runtime",
            }
        )
        return {
            "history_cards": [],
            "messages": [],
            "claims": [],
            "open_questions": [],
            "agent_outputs": {},
            "consensus_reached": False,
            "executed_rounds": 0,
            "current_round": 0,
            "continue_next_round": False,
            "agent_commands": {},
            "next_step": "",
            "round_start_turn_index": 0,
            "discussion_step_count": 0,
            "max_discussion_steps": self.MAX_DISCUSSION_STEPS_PER_ROUND,
            "supervisor_stop_requested": False,
            "supervisor_stop_reason": "",
            "supervisor_notes": [],
        }

    def _route_after_analysis_parallel(self, state: _DebateExecState) -> str:
        return "analysis_collaboration" if settings.DEBATE_ENABLE_COLLABORATION else "critic"

    def _route_after_critic(self, state: _DebateExecState) -> str:
        return "rebuttal" if settings.DEBATE_ENABLE_CRITIQUE else "judge"

    def _supervisor_step_to_node(self, next_step: str) -> str:
        return supervisor_step_to_node_route(next_step)

    def _route_after_supervisor_decide(self, state: _DebateExecState) -> str:
        return self._supervisor_step_to_node(str(state.get("next_step") or ""))

    def _route_after_round_evaluate(self, state: _DebateExecState) -> str:
        return "round_start" if bool(state.get("continue_next_round")) else "finalize"

    def _round_discussion_budget(self) -> int:
        base = self.MAX_DISCUSSION_STEPS_PER_ROUND
        if settings.DEBATE_ENABLE_COLLABORATION:
            base += 2
        if not settings.DEBATE_ENABLE_CRITIQUE:
            base = max(6, base - 2)
        return max(6, min(base, 24))

    def _step_for_agent(self, agent_name: str) -> str:
        return step_for_agent_route(agent_name)

    def _agent_from_step(self, step: str) -> str:
        return agent_from_step_route(step)

    def _round_turns_from_state(self, state: _DebateExecState) -> List[DebateTurn]:
        start_index = max(0, int(state.get("round_start_turn_index") or 0))
        return list(self.turns[start_index:])

    def _round_cards_from_state(self, state: _DebateExecState) -> List[AgentEvidence]:
        history_cards = list(state.get("history_cards") or [])
        start_index = max(0, int(state.get("round_start_turn_index") or 0))
        if start_index <= 0:
            return history_cards
        # round_start_turn_index is indexed against self.turns; cards track the same append order.
        return history_cards[start_index:]

    def _recent_judge_turn(self, round_turns: List[DebateTurn]) -> Optional[DebateTurn]:
        for turn in reversed(round_turns):
            if turn.agent_name == "JudgeAgent":
                return turn
        return None

    def _recent_judge_card(self, round_cards: List[AgentEvidence]) -> Optional[AgentEvidence]:
        for card in reversed(round_cards):
            if card.agent_name == "JudgeAgent":
                return card
        return None

    def _recent_agent_card(
        self,
        round_cards: List[AgentEvidence],
        agent_name: str,
    ) -> Optional[AgentEvidence]:
        return recent_agent_card_route(round_cards, agent_name)

    def _round_agent_counts(self, round_cards: List[AgentEvidence]) -> Dict[str, int]:
        return round_agent_counts_route(round_cards)

    def _judge_is_ready(self, round_cards: List[AgentEvidence]) -> bool:
        return judge_is_ready_route(
            round_cards,
            parallel_analysis_agents=self.PARALLEL_ANALYSIS_AGENTS,
            debate_enable_critique=settings.DEBATE_ENABLE_CRITIQUE,
        )

    def _route_guardrail(
        self,
        *,
        state: _DebateExecState,
        round_cards: List[AgentEvidence],
        route_decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        return route_guardrail_helper(
            state=state,
            round_cards=round_cards,
            route_decision=route_decision,
            consensus_threshold=self.consensus_threshold,
            max_discussion_steps_default=self.MAX_DISCUSSION_STEPS_PER_ROUND,
            parallel_analysis_agents=self.PARALLEL_ANALYSIS_AGENTS,
            debate_enable_critique=settings.DEBATE_ENABLE_CRITIQUE,
        )

    def _fallback_supervisor_route(
        self,
        state: _DebateExecState,
        round_cards: List[AgentEvidence],
    ) -> Dict[str, Any]:
        return fallback_supervisor_route_helper(
            state=state,
            round_cards=round_cards,
            debate_enable_critique=settings.DEBATE_ENABLE_CRITIQUE,
            consensus_threshold=self.consensus_threshold,
            max_discussion_steps_default=self.MAX_DISCUSSION_STEPS_PER_ROUND,
            parallel_analysis_agents=self.PARALLEL_ANALYSIS_AGENTS,
        )

    def _route_from_commander_output(
        self,
        payload: Dict[str, Any],
        state: _DebateExecState,
        round_cards: List[AgentEvidence],
    ) -> Dict[str, Any]:
        return route_from_commander_output_helper(
            payload=payload,
            state=state,
            round_cards=round_cards,
            allowed_agents=[spec.name for spec in self._agent_sequence()],
            is_placeholder_summary=self._is_placeholder_summary,
            fallback_supervisor_route_fn=self._fallback_supervisor_route,
            route_guardrail_fn=self._route_guardrail,
        )

    def _card_to_ai_message(self, card: AgentEvidence) -> Optional[AIMessage]:
        output = card.raw_output if isinstance(getattr(card, "raw_output", None), dict) else {}
        chat_message = str(output.get("chat_message") or "").strip()
        if not chat_message:
            return None
        return AIMessage(
            content=chat_message[:1200],
            name=card.agent_name,
            additional_kwargs={
                "agent_name": card.agent_name,
                "phase": card.phase,
                "round_number": None,
                "confidence": float(card.confidence or 0.0),
                "conclusion": str(card.conclusion or "")[:220],
            },
        )

    def _dialogue_items_from_messages(
        self,
        messages: List[Any],
        *,
        limit: int = 8,
        char_budget: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        budget = max(240, int(char_budget or self.DIALOGUE_PROMPT_CHAR_BUDGET))
        items: List[Dict[str, Any]] = []
        seen_signatures: set[tuple[str, str]] = set()
        used_chars = 0
        for msg in reversed(list(messages or [])):
            content = getattr(msg, "content", "")
            if isinstance(content, list):
                content_text = " ".join(
                    str(part.get("text") or "")
                    for part in content
                    if isinstance(part, dict)
                ).strip()
            else:
                content_text = str(content or "").strip()
            if not content_text:
                continue
            additional = getattr(msg, "additional_kwargs", {}) or {}
            speaker = (
                str(getattr(msg, "name", "") or "")
                or str(additional.get("agent_name") or "")
                or str(getattr(msg, "type", "") or "assistant")
            )
            # Avoid flooding prompts with repeated statements from the same speaker.
            sig = (speaker, content_text[:64])
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)
            msg_snippet = content_text[:140]
            conclusion_snippet = str(additional.get("conclusion") or "")[:96]
            estimated = len(msg_snippet) + len(conclusion_snippet) + len(speaker) + 24
            if items and used_chars + estimated > budget:
                continue
            used_chars += estimated
            items.append(
                {
                    "speaker": speaker,
                    "phase": str(additional.get("phase") or ""),
                    "conclusion": conclusion_snippet,
                    "message": msg_snippet,
                }
            )
            if len(items) >= max(1, limit):
                break
        items.reverse()
        return items

    def _message_deltas_from_cards(self, cards: List[AgentEvidence]) -> List[AIMessage]:
        deltas: List[AIMessage] = []
        for card in cards:
            msg = self._card_to_ai_message(card)
            if msg is not None:
                deltas.append(msg)
        return deltas

    def _derive_conversation_state(self, history_cards: List[AgentEvidence]) -> Dict[str, Any]:
        claims: List[Dict[str, Any]] = []
        open_questions: List[str] = []
        agent_outputs: Dict[str, Dict[str, Any]] = {}
        for card in history_cards:
            output = card.raw_output if isinstance(getattr(card, "raw_output", None), dict) else {}
            agent_outputs[card.agent_name] = output
            conclusion = str(card.conclusion or output.get("conclusion") or "").strip()
            if conclusion:
                claims.append(
                    {
                        "agent_name": card.agent_name,
                        "phase": card.phase,
                        "round_number": None,
                        "conclusion": conclusion,
                        "confidence": float(card.confidence or 0.0),
                    }
                )
            for key in ("missing_info", "open_questions", "needs_validation"):
                value = output.get(key)
                if isinstance(value, list):
                    for item in value:
                        text = str(item or "").strip()
                        if text:
                            open_questions.append(text)
                elif isinstance(value, str):
                    text = value.strip()
                    if text:
                        open_questions.append(text)
        # preserve order while deduping
        deduped_questions = list(dict.fromkeys(open_questions))[:12]
        return {
            "claims": claims[-24:],
            "open_questions": deduped_questions,
            "agent_outputs": agent_outputs,
        }

    async def _graph_supervisor_decide(self, state: _DebateExecState) -> _DebateExecState:
        history_cards = list(state.get("history_cards") or [])
        prev_history_count = len(history_cards)
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=6,
            char_budget=720,
        )
        loop_round = int(state.get("current_round") or 1)
        discussion_step_count = int(state.get("discussion_step_count") or 0)
        max_discussion_steps = int(state.get("max_discussion_steps") or self.MAX_DISCUSSION_STEPS_PER_ROUND)
        round_cards = self._round_cards_from_state(state)
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
            recent_judge_card = self._recent_judge_card(round_cards)
            recent_judge_conf = float(recent_judge_card.confidence or 0.0) if recent_judge_card else 0.0
            if recent_judge_card and recent_judge_conf >= self.consensus_threshold:
                route_decision = {
                    "next_step": "",
                    "should_stop": True,
                    "stop_reason": "JudgeAgent 已给出高置信裁决",
                    "reason": "达到裁决阈值，主Agent结束讨论",
                }
                mode = "langgraph_supervisor_consensus_shortcut"
            elif discussion_step_count >= max_discussion_steps:
                route_decision = self._fallback_supervisor_route(state=state, round_cards=round_cards)
                route_decision["reason"] = f"达到讨论步数预算({max_discussion_steps})，使用回退调度"
                mode = "langgraph_supervisor_budget_guard"
            else:
                context_summary = state.get("context_summary") or {}
                compact_context = self._compact_round_context(context_summary)
                round_cards = list(history_cards[-10:])
                try:
                    commander_output = await self._run_problem_analysis_supervisor_router(
                        loop_round=loop_round,
                        compact_context=compact_context,
                        history_cards=history_cards,
                        round_history_cards=round_cards,
                        dialogue_items=dialogue_items,
                        discussion_step_count=discussion_step_count,
                        max_discussion_steps=max_discussion_steps,
                    )
                    route_decision = self._route_from_commander_output(
                        payload=commander_output,
                        state=state,
                        round_cards=self._round_cards_from_state(state),
                    )
                    merged_commands = dict(state.get("agent_commands") or {})
                    merged_commands.update(dict(commander_output.get("commands") or {}))
                    route_decision["agent_commands"] = merged_commands
                except Exception as exc:
                    logger.warning(
                        "supervisor_dynamic_routing_failed",
                        session_id=self.session_id,
                        loop_round=loop_round,
                        error=str(exc).strip() or exc.__class__.__name__,
                    )
                    route_decision = self._fallback_supervisor_route(state=state, round_cards=round_cards)
                    mode = "langgraph_supervisor_fallback"

        route_decision = self._route_guardrail(
            state=state,
            round_cards=self._round_cards_from_state({"history_cards": history_cards, "round_start_turn_index": state.get("round_start_turn_index")}),
            route_decision=route_decision,
        )

        convo_state = self._derive_conversation_state(history_cards)
        message_deltas = self._message_deltas_from_cards(history_cards[prev_history_count:])
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
        await self._emit_event(
            {
                "type": "supervisor_decision",
                "session_id": self.session_id,
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

    def _graph_apply_step_result(
        self,
        state: _DebateExecState,
        result: Optional[Dict[str, Any]],
    ) -> _DebateExecState:
        prev_history_cards = list(state.get("history_cards") or [])
        next_history_cards = list((result or {}).get("history_cards") or state.get("history_cards") or [])
        message_deltas = self._message_deltas_from_cards(next_history_cards[len(prev_history_cards):])
        return {
            **(result or {}),
            "next_step": "",
            "discussion_step_count": int(state.get("discussion_step_count") or 0) + 1,
            **({"messages": message_deltas} if message_deltas else {}),
            **self._derive_conversation_state(next_history_cards),
        }

    async def _graph_round_start(self, state: _DebateExecState) -> _DebateExecState:
        current_round = int(state.get("current_round") or 0) + 1
        if current_round > max(1, self.max_rounds):
            return {"continue_next_round": False}
        history_cards = list(state.get("history_cards") or [])
        prev_history_count = len(history_cards)
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=4,
            char_budget=520,
        )
        context_summary = state.get("context_summary") or {}
        compact_context = self._compact_round_context(context_summary)
        await self._emit_event(
            {
                "type": "round_started",
                "loop_round": current_round,
                "max_rounds": self.max_rounds,
                "mode": "langgraph_runtime",
            }
        )
        commander_result = await self._run_problem_analysis_commander(
            loop_round=current_round,
            compact_context=compact_context,
            history_cards=history_cards,
            dialogue_items=dialogue_items,
        )
        commands = dict(commander_result.get("commands") or {})
        self._active_round_commands = commands
        preseed_route = self._route_from_commander_output(
            payload=commander_result,
            state=state,
            round_cards=self._round_cards_from_state({"history_cards": history_cards, "round_start_turn_index": len(self.turns) - 1}),
        )
        return {
            "current_round": current_round,
            "continue_next_round": False,
            "history_cards": history_cards,
            "agent_commands": commands,
            "next_step": str(preseed_route.get("next_step") or ""),
            "round_start_turn_index": len(self.turns),
            "discussion_step_count": 0,
            "max_discussion_steps": self._round_discussion_budget(),
            "supervisor_stop_requested": bool(preseed_route.get("should_stop") or False),
            "supervisor_stop_reason": str(preseed_route.get("stop_reason") or ""),
            **(
                {"messages": self._message_deltas_from_cards(history_cards[prev_history_count:])}
                if len(history_cards) > prev_history_count
                else {}
            ),
            **self._derive_conversation_state(history_cards),
        }

    async def _graph_analysis_parallel(self, state: _DebateExecState) -> _DebateExecState:
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=4,
            char_budget=520,
        )
        compact_context = self._compact_round_context(context_summary)
        await self._run_parallel_analysis_phase(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
        )
        return {"history_cards": history_cards}

    async def _graph_analysis_collaboration(self, state: _DebateExecState) -> _DebateExecState:
        if not settings.DEBATE_ENABLE_COLLABORATION:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=5,
            char_budget=620,
        )
        compact_context = self._compact_round_context(context_summary)
        await self._run_collaboration_phase(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            dialogue_items=dialogue_items,
        )
        return {"history_cards": history_cards}

    async def _graph_critic(self, state: _DebateExecState) -> _DebateExecState:
        if not settings.DEBATE_ENABLE_CRITIQUE:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=5,
            char_budget=620,
        )
        compact_context = self._compact_round_context(context_summary)
        await execute_single_phase_agent(
            self,
            agent_name="CriticAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
        )
        return {"history_cards": history_cards}

    async def _graph_rebuttal(self, state: _DebateExecState) -> _DebateExecState:
        if not settings.DEBATE_ENABLE_CRITIQUE:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=5,
            char_budget=620,
        )
        compact_context = self._compact_round_context(context_summary)
        await execute_single_phase_agent(
            self,
            agent_name="RebuttalAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
        )
        return {"history_cards": history_cards}

    async def _graph_judge(self, state: _DebateExecState) -> _DebateExecState:
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=6,
            char_budget=760,
        )
        compact_context = self._compact_round_context(context_summary)
        await execute_single_phase_agent(
            self,
            agent_name="JudgeAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
        )
        await self._emit_problem_analysis_final_summary(
            loop_round=loop_round,
            history_cards=history_cards,
        )
        return {"history_cards": history_cards}

    async def _graph_round_evaluate(self, state: _DebateExecState) -> _DebateExecState:
        current_round = int(state.get("current_round") or 1)
        history_cards = list(state.get("history_cards") or [])
        judge_card = self._recent_judge_card(self._round_cards_from_state(state))
        judge_confidence = float((judge_card.confidence if judge_card else 0.0) or 0.0)
        supervisor_stop_requested = bool(state.get("supervisor_stop_requested") or False)
        consensus_reached = bool(judge_card) and judge_confidence >= self.consensus_threshold
        executed_rounds = max(int(state.get("executed_rounds") or 0), current_round)
        await self._emit_event(
            {
                "type": "round_completed",
                "loop_round": current_round,
                "consensus_reached": consensus_reached,
                "judge_confidence": judge_confidence,
                "supervisor_stop_requested": supervisor_stop_requested,
                "supervisor_stop_reason": str(state.get("supervisor_stop_reason") or "")[:240],
                "mode": "langgraph_runtime",
            }
        )
        continue_next_round = (
            (not consensus_reached or current_round < self.min_rounds)
            and current_round < max(1, self.max_rounds)
            and not supervisor_stop_requested
        )
        return {
            "history_cards": history_cards,
            "consensus_reached": consensus_reached,
            "executed_rounds": executed_rounds,
            "continue_next_round": continue_next_round,
        }

    def _spec_by_name(self, agent_name: str) -> Optional[AgentSpec]:
        for spec in self._agent_sequence():
            if spec.name == agent_name:
                return spec
        return None

    def _problem_analysis_agent_spec(self) -> AgentSpec:
        return build_problem_analysis_agent_spec()

    def _coordinator_command_schema(self) -> Dict[str, Any]:
        return coordinator_command_schema_template()

    def _build_problem_analysis_commander_prompt(
        self,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        return build_problem_analysis_commander_prompt_template(
            loop_round=loop_round,
            max_rounds=self.max_rounds,
            context=context,
            history_cards=history_cards,
            dialogue_items=dialogue_items,
            to_json=self._to_compact_json,
        )

    def _build_problem_analysis_supervisor_prompt(
        self,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_history_cards: List[AgentEvidence],
        discussion_step_count: int,
        max_discussion_steps: int,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        open_questions = self._derive_conversation_state(history_cards).get("open_questions") or []
        return build_problem_analysis_supervisor_prompt_template(
            loop_round=loop_round,
            max_rounds=self.max_rounds,
            context=context,
            round_history_cards=round_history_cards,
            open_questions=open_questions,
            dialogue_items=dialogue_items,
            discussion_step_count=discussion_step_count,
            max_discussion_steps=max_discussion_steps,
            to_json=self._to_compact_json,
        )

    def _extract_agent_commands_from_payload(
        self,
        payload: Dict[str, Any],
        *,
        fill_defaults: bool,
        targets_hint: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        raw_commands = payload.get("commands")
        commands: Dict[str, Dict[str, Any]] = {}
        if isinstance(raw_commands, list):
            for item in raw_commands:
                if not isinstance(item, dict):
                    continue
                target = str(item.get("target_agent") or "").strip()
                if not target:
                    continue
                commands[target] = {
                    "target_agent": target,
                    "task": str(item.get("task") or "").strip(),
                    "focus": str(item.get("focus") or "").strip(),
                    "expected_output": str(item.get("expected_output") or "").strip(),
                }

        defaults = {
            "LogAgent": "分析错误日志、502 与 CPU 异常的直接证据链",
            "DomainAgent": "根据接口 URL 映射领域/聚合根/责任田并确认负责团队",
            "CodeAgent": "定位可能代码瓶颈、连接池/线程池/慢SQL风险点",
            "CriticAgent": "质疑前述结论中的证据缺口和假设跳跃",
            "RebuttalAgent": "针对质疑补充证据并收敛执行建议",
            "JudgeAgent": "综合所有结论给出最终根因裁决与处置建议",
        }
        if fill_defaults:
            for target, task in defaults.items():
                commands.setdefault(
                    target,
                    {
                        "target_agent": target,
                        "task": task,
                        "focus": "",
                        "expected_output": "",
                    },
                )
        elif targets_hint:
            for target in targets_hint:
                if target in defaults and target not in commands:
                    commands[target] = {
                        "target_agent": target,
                        "task": defaults[target],
                        "focus": "",
                        "expected_output": "",
                    }
        return commands

    async def _run_problem_analysis_commander(
        self,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        spec = self._problem_analysis_agent_spec()
        round_number = len(self.turns) + 1
        await self._emit_event(
            {
                "type": "agent_chat_message",
                "phase": spec.phase,
                "agent_name": spec.name,
                "agent_role": spec.role,
                "model": settings.llm_model,
                "session_id": self.session_id,
                "loop_round": loop_round,
                "round_number": round_number,
                "message": "我先做问题初步分析，并给各专家Agent分派任务。",
                "confidence": 0.0,
                "conclusion": "",
                "reply_to": "all",
            }
        )
        prompt = self._build_problem_analysis_commander_prompt(
            loop_round=loop_round,
            context=compact_context,
            history_cards=history_cards,
            dialogue_items=dialogue_items,
        )
        try:
            turn = await execute_runtime_agent_call(
                self,
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
                history_cards_context=history_cards,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            turn = await self._create_fallback_turn(
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
                error_text=error_text,
            )
        await self._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)

        payload = turn.output_content if isinstance(turn.output_content, dict) else {}
        commands = self._extract_agent_commands_from_payload(payload, fill_defaults=True)
        return {
            "commands": commands,
            "next_mode": str(payload.get("next_mode") or "").strip().lower(),
            "next_agent": str(payload.get("next_agent") or "").strip(),
            "should_stop": bool(payload.get("should_stop") or False),
            "stop_reason": str(payload.get("stop_reason") or "").strip(),
        }

    async def _run_problem_analysis_supervisor_router(
        self,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_history_cards: List[AgentEvidence],
        discussion_step_count: int,
        max_discussion_steps: int,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        spec = self._problem_analysis_agent_spec()
        round_number = len(self.turns) + 1
        await self._emit_event(
            {
                "type": "agent_chat_message",
                "phase": spec.phase,
                "agent_name": spec.name,
                "agent_role": spec.role,
                "model": settings.llm_model,
                "session_id": self.session_id,
                "loop_round": loop_round,
                "round_number": round_number,
                "message": "我在检查当前证据和分歧，决定下一位发言者。",
                "confidence": 0.0,
                "conclusion": "",
                "reply_to": "all",
            }
        )
        prompt = self._build_problem_analysis_supervisor_prompt(
            loop_round=loop_round,
            context=compact_context,
            history_cards=history_cards,
            round_history_cards=round_history_cards,
            dialogue_items=dialogue_items,
            discussion_step_count=discussion_step_count,
            max_discussion_steps=max_discussion_steps,
        )
        try:
            turn = await execute_runtime_agent_call(
                self,
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
                history_cards_context=history_cards,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            turn = await self._create_fallback_turn(
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
                error_text=error_text,
            )
        await self._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
        payload = turn.output_content if isinstance(turn.output_content, dict) else {}
        next_agent = str(payload.get("next_agent") or "").strip()
        targets_hint: List[str] = []
        next_mode = str(payload.get("next_mode") or "").strip().lower()
        if next_mode in ("parallel_analysis", "analysis_parallel"):
            targets_hint = list(self.PARALLEL_ANALYSIS_AGENTS)
        elif next_agent:
            targets_hint = [next_agent]
        commands = self._extract_agent_commands_from_payload(
            payload,
            fill_defaults=False,
            targets_hint=targets_hint,
        )
        return {
            "commands": commands,
            "next_mode": next_mode,
            "next_agent": next_agent,
            "should_stop": bool(payload.get("should_stop") or False),
            "stop_reason": str(payload.get("stop_reason") or "").strip(),
        }

    async def _emit_agent_command_issued(
        self,
        commander: str,
        target: str,
        loop_round: int,
        round_number: int,
        command: Dict[str, Any],
    ) -> None:
        command_text = str(command.get("task") or "").strip() or f"请完成 {target} 维度分析"
        focus = str(command.get("focus") or "").strip()
        expected = str(command.get("expected_output") or "").strip()
        message_parts = [f"{commander} 指令 {target}: {command_text}"]
        if focus:
            message_parts.append(f"重点: {focus}")
        if expected:
            message_parts.append(f"输出: {expected}")
        await self._emit_event(
            {
                "type": "agent_command_issued",
                "phase": "orchestration",
                "agent_name": commander,
                "target_agent": target,
                "loop_round": loop_round,
                "round_number": round_number,
                "command": command_text,
                "message": "\n".join(message_parts),
                "session_id": self.session_id,
            }
        )

    async def _emit_agent_command_feedback(
        self,
        source: str,
        loop_round: int,
        round_number: int,
        command: Dict[str, Any],
        turn: DebateTurn,
    ) -> None:
        output = turn.output_content if isinstance(turn.output_content, dict) else {}
        feedback_text = str(output.get("chat_message") or output.get("conclusion") or "")[:300]
        await self._emit_event(
            {
                "type": "agent_command_feedback",
                "phase": turn.phase,
                "agent_name": source,
                "target_agent": "ProblemAnalysisAgent",
                "loop_round": loop_round,
                "round_number": round_number,
                "command": str(command.get("task") or "")[:240],
                "feedback": feedback_text,
                "message": f"{source} 已执行主Agent命令并提交结论",
                "session_id": self.session_id,
                "confidence": float(turn.confidence or 0.0),
            }
        )

    async def _emit_problem_analysis_final_summary(
        self,
        loop_round: int,
        history_cards: Optional[List[AgentEvidence]] = None,
    ) -> None:
        judge_turn = next((turn for turn in reversed(self.turns) if turn.agent_name == "JudgeAgent"), None)
        if not judge_turn:
            return
        cards = list(history_cards or self._history_cards_snapshot())
        output = judge_turn.output_content if isinstance(judge_turn.output_content, dict) else {}
        final_judgment = output.get("final_judgment") if isinstance(output.get("final_judgment"), dict) else {}
        root_cause = final_judgment.get("root_cause") if isinstance(final_judgment, dict) else {}
        root_summary = str((root_cause or {}).get("summary") or "").strip()
        summary_confidence = float(output.get("confidence") or judge_turn.confidence or 0.0)
        if self._is_placeholder_summary(root_summary):
            final_payload = self._build_final_payload(
                history_cards=cards,
                consensus_reached=False,
                executed_rounds=max(1, int(loop_round or 1)),
            )
            payload_judgment = (
                final_payload.get("final_judgment")
                if isinstance(final_payload.get("final_judgment"), dict)
                else {}
            )
            payload_root = (
                payload_judgment.get("root_cause")
                if isinstance(payload_judgment, dict)
                else {}
            )
            payload_root_summary = str((payload_root or {}).get("summary") or "").strip()
            if payload_root_summary and not self._is_placeholder_summary(payload_root_summary):
                root_summary = payload_root_summary
                summary_confidence = float(final_payload.get("confidence") or summary_confidence or 0.0)
        judge_chat = str(output.get("chat_message") or "").strip()
        if not root_summary and not judge_chat:
            return
        message_text = (
            f"我已汇总各专家反馈，当前结论：{root_summary}"
            if root_summary
            else f"我已汇总各专家反馈，{judge_chat}"
        )
        await self._emit_event(
            {
                "type": "agent_chat_message",
                "phase": "judgment",
                "agent_name": "ProblemAnalysisAgent",
                "agent_role": "问题分析主Agent/调度协调者",
                "model": settings.llm_model,
                "session_id": self.session_id,
                "loop_round": loop_round,
                "round_number": len(self.turns),
                "message": message_text[:1200],
                "confidence": summary_confidence,
                "conclusion": root_summary[:220],
                "reply_to": "all",
            }
        )

    async def _run_parallel_analysis_phase(
        self,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        agent_commands: Optional[Dict[str, Dict[str, Any]]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        parallel_names = set(self.PARALLEL_ANALYSIS_AGENTS)
        parallel_specs = [
            spec for spec in self._agent_sequence() if spec.phase == "analysis" and spec.name in parallel_names
        ]
        if not parallel_specs:
            return
        round_cursor = len(self.turns) + 1
        parallel_inputs: List[tuple[AgentSpec, int, str, Dict[str, Any]]] = []
        parallel_history = list(history_cards)
        for spec in parallel_specs:
            round_number = round_cursor
            round_cursor += 1
            assigned_command = (agent_commands or {}).get(spec.name)
            prompt = self._build_agent_prompt(
                spec=spec,
                loop_round=loop_round,
                context=compact_context,
                history_cards=parallel_history,
                assigned_command=assigned_command,
                dialogue_items=dialogue_items,
            )
            parallel_inputs.append((spec, round_number, prompt, assigned_command or {}))

        await self._emit_event(
            {
                "type": "parallel_analysis_started",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": self.session_id,
                "agents": [spec.name for spec, _, _, _ in parallel_inputs],
            }
        )
        for spec, round_number, _, assigned_command in parallel_inputs:
            if assigned_command:
                await self._emit_agent_command_issued(
                    commander="ProblemAnalysisAgent",
                    target=spec.name,
                    loop_round=loop_round,
                    round_number=round_number,
                    command=assigned_command,
                )
        parallel_tasks = [
            asyncio.create_task(
                execute_runtime_agent_call(
                    self,
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    history_cards_context=history_cards,
                )
            )
            for spec, round_number, prompt, _ in parallel_inputs
        ]
        parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
        for (spec, round_number, prompt, assigned_command), result in zip(parallel_inputs, parallel_results):
            if isinstance(result, Exception):
                error_text = str(result).strip() or result.__class__.__name__
                turn = await self._create_fallback_turn(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    error_text=error_text,
                )
            else:
                turn = result
            await self._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
            if assigned_command:
                await self._emit_agent_command_feedback(
                    source=spec.name,
                    loop_round=loop_round,
                    round_number=round_number,
                    command=assigned_command,
                    turn=turn,
                )
        await self._emit_event(
            {
                "type": "parallel_analysis_completed",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": self.session_id,
                "agents": [spec.name for spec, _, _, _ in parallel_inputs],
            }
        )

    async def _run_collaboration_phase(
        self,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        parallel_specs = [
            spec
            for spec in self._agent_sequence()
            if spec.phase == "analysis" and spec.name in set(self.PARALLEL_ANALYSIS_AGENTS)
        ]
        if not parallel_specs:
            return
        peer_cards = self._latest_cards_for_agents(
            history_cards=history_cards,
            agent_names=[spec.name for spec in parallel_specs],
            limit=self.COLLABORATION_PEER_LIMIT,
        )
        round_cursor = len(self.turns) + 1
        collab_inputs: List[tuple[AgentSpec, int, str]] = []
        for spec in parallel_specs:
            round_number = round_cursor
            round_cursor += 1
            prompt = self._build_collaboration_prompt(
                spec=spec,
                loop_round=loop_round,
                context=compact_context,
                peer_cards=peer_cards,
                dialogue_items=dialogue_items,
            )
            collab_inputs.append((spec, round_number, prompt))

        await self._emit_event(
            {
                "type": "parallel_analysis_collaboration_started",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": self.session_id,
                "agents": [spec.name for spec, _, _ in collab_inputs],
            }
        )
        collab_tasks = [
            asyncio.create_task(
                execute_runtime_agent_call(
                    self,
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    history_cards_context=history_cards,
                )
            )
            for spec, round_number, prompt in collab_inputs
        ]
        collab_results = await asyncio.gather(*collab_tasks, return_exceptions=True)
        for (spec, round_number, prompt), result in zip(collab_inputs, collab_results):
            if isinstance(result, Exception):
                error_text = str(result).strip() or result.__class__.__name__
                turn = await self._create_fallback_turn(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    error_text=error_text,
                )
            else:
                turn = result
            await self._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
        await self._emit_event(
            {
                "type": "parallel_analysis_collaboration_completed",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": self.session_id,
                "agents": [spec.name for spec, _, _ in collab_inputs],
            }
        )

    async def _graph_finalize(self, state: _DebateExecState) -> _DebateExecState:
        history_cards = list(state.get("history_cards") or [])
        consensus_reached = bool(state.get("consensus_reached") or False)
        executed_rounds = int(state.get("executed_rounds") or state.get("current_round") or 0)
        final_payload = dict(state.get("final_payload") or {})
        if not final_payload:
            final_payload = self._build_final_payload(
                history_cards=history_cards,
                consensus_reached=consensus_reached,
                executed_rounds=executed_rounds,
            )
        await runtime_session_store.complete(
            str(self.session_id),
            FinalVerdict.model_validate(final_payload.get("final_judgment") or {}),
        )
        await self._emit_event(
            {
                "type": "runtime_debate_completed",
                "confidence": final_payload.get("confidence", 0.0),
                "consensus_reached": consensus_reached,
                "mode": "langgraph_runtime",
            }
        )
        return {"final_payload": final_payload}

    def _build_peer_driven_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        peer_items = self._collect_peer_items(
            history_cards=history_cards,
            exclude_agent=spec.name,
            limit=max(2, self.MAX_HISTORY_ITEMS + 1),
        )
        return build_peer_driven_prompt_template(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self.max_rounds,
            context=context,
            peer_items=peer_items,
            assigned_command=assigned_command,
            dialogue_items=dialogue_items,
            to_json=self._to_compact_json,
        )

    def _judge_output_schema(self) -> Dict[str, Any]:
        return judge_output_schema_template()

    def _collect_peer_items(
        self,
        history_cards: List[AgentEvidence],
        exclude_agent: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        peers: List[Dict[str, Any]] = []
        for card in reversed(history_cards):
            if card.agent_name == exclude_agent:
                continue
            peers.append(
                {
                    "agent": card.agent_name,
                    "phase": card.phase,
                    "summary": card.summary[:72],
                    "conclusion": card.conclusion[:100],
                    "confidence": round(float(card.confidence), 3),
                }
            )
            if len(peers) >= max(1, limit):
                break
        peers.reverse()
        return peers

    def _latest_cards_for_agents(
        self,
        history_cards: List[AgentEvidence],
        agent_names: List[str],
        limit: int,
    ) -> List[AgentEvidence]:
        wanted = set(agent_names)
        latest_by_agent: Dict[str, AgentEvidence] = {}
        for card in reversed(history_cards):
            if card.agent_name in wanted and card.agent_name not in latest_by_agent:
                latest_by_agent[card.agent_name] = card
            if len(latest_by_agent) >= len(wanted):
                break
        ordered = [
            latest_by_agent[name]
            for name in agent_names
            if name in latest_by_agent
        ]
        return ordered[: max(1, limit)]

    async def _create_fallback_turn(
        self,
        spec: AgentSpec,
        prompt: str,
        round_number: int,
        loop_round: int,
        error_text: str,
    ) -> DebateTurn:
        friendly_reason = self._friendly_degrade_reason(error_text)
        await self._emit_event(
            {
                "type": "agent_round_skipped",
                "phase": spec.phase,
                "agent_name": spec.name,
                "agent_role": spec.role,
                "loop_round": loop_round,
                "round_number": round_number,
                "reason": friendly_reason,
                "session_id": self.session_id,
            }
        )
        fallback_output = (
            normalize_judge_output(
                {},
                f"{spec.name} {friendly_reason}",
                fallback_summary=self.JUDGE_FALLBACK_SUMMARY,
            )
            if spec.name == "JudgeAgent"
            else normalize_normal_output(
                {},
                f"{spec.name} {friendly_reason}",
            )
        )
        now = datetime.utcnow()
        return DebateTurn(
            round_number=round_number,
            phase=spec.phase,
            agent_name=spec.name,
            agent_role=spec.role,
            model={"name": settings.llm_model},
            input_message=prompt,
            output_content=fallback_output,
            confidence=float(fallback_output.get("confidence", 0.0) or 0.0),
            started_at=now,
            completed_at=now,
        )

    @staticmethod
    def _friendly_degrade_reason(error_text: str) -> str:
        normalized = str(error_text or "").strip().lower()
        if "timeout" in normalized:
            return "调用超时，已降级继续"
        if (
            "429" in normalized
            or "toomanyrequests" in normalized
            or "serveroverloaded" in normalized
            or "rate limit" in normalized
        ):
            return "调用被限流，已降级继续"
        return "调用异常，已降级继续"

    def _history_cards_snapshot(self, limit: int = 8) -> List[AgentEvidence]:
        cards: List[AgentEvidence] = []
        for turn in self.turns[-max(1, limit) :]:
            output = turn.output_content if isinstance(turn.output_content, dict) else {}
            cards.append(
                AgentEvidence(
                    agent_name=turn.agent_name,
                    phase=turn.phase,
                    summary=str(output.get("analysis") or "")[:200],
                    conclusion=str(output.get("conclusion") or "")[:220],
                    evidence_chain=[str(item) for item in (output.get("evidence_chain") or [])[:3]],
                    confidence=float(turn.confidence or 0.0),
                    raw_output=output,
                )
            )
        return cards

    def _infer_reply_target(
        self,
        spec_name: str,
        history_cards: List[AgentEvidence],
    ) -> Optional[str]:
        if spec_name == "ProblemAnalysisAgent":
            return "all"
        if spec_name == "JudgeAgent":
            return "all"
        if spec_name == "RebuttalAgent":
            for card in reversed(history_cards):
                if card.agent_name == "CriticAgent":
                    return "CriticAgent"
        for card in reversed(history_cards):
            if card.agent_name != spec_name:
                return card.agent_name
        return None

    async def _record_turn(
        self,
        turn: DebateTurn,
        loop_round: int,
        history_cards: List[AgentEvidence],
    ) -> None:
        self.turns.append(turn)
        card = AgentEvidence(
            agent_name=turn.agent_name,
            phase=turn.phase,
            summary=str(turn.output_content.get("analysis") or "")[:200],
            conclusion=str(turn.output_content.get("conclusion") or "")[:220],
            evidence_chain=[str(item) for item in (turn.output_content.get("evidence_chain") or [])[:3]],
            confidence=float(turn.confidence or 0.0),
            raw_output=turn.output_content,
        )
        history_cards.append(card)
        if len(history_cards) > 20:
            del history_cards[:-20]

        await runtime_session_store.append_round(
            self.session_id,
            RoundCheckpoint(
                session_id=self.session_id,
                round_number=turn.round_number,
                loop_round=loop_round,
                phase=turn.phase,
                agent_name=turn.agent_name,
                confidence=turn.confidence,
                summary=card.summary,
                conclusion=card.conclusion,
            ),
        )

    def _agent_sequence(self) -> List[AgentSpec]:
        return build_agent_sequence(enable_critique=bool(settings.DEBATE_ENABLE_CRITIQUE))

    def _build_agent_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        return build_agent_prompt_template(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self.max_rounds,
            max_history_items=self.MAX_HISTORY_ITEMS,
            context=context,
            history_cards=history_cards,
            assigned_command=assigned_command,
            dialogue_items=dialogue_items,
            to_json=self._to_compact_json,
        )

    def _build_collaboration_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        peer_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        return build_collaboration_prompt_template(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self.max_rounds,
            context=context,
            peer_cards=peer_cards,
            assigned_command=assigned_command,
            dialogue_items=dialogue_items,
            to_json=self._to_compact_json,
        )

    def _compact_round_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        interface_mapping = context.get("interface_mapping")
        if not isinstance(interface_mapping, dict):
            interface_mapping = {}

        matched_endpoint = interface_mapping.get("matched_endpoint")
        if not isinstance(matched_endpoint, dict):
            matched_endpoint = {}

        parsed_data = context.get("parsed_data")
        if not isinstance(parsed_data, dict):
            parsed_data = {}

        compact_parsed: Dict[str, Any] = {}
        important_keys = (
            "service",
            "status_code",
            "error_type",
            "error_message",
            "exception_class",
            "exception_message",
            "cpu_usage",
            "latency_ms",
            "host",
            "pod",
            "trace_id",
        )
        for key in important_keys:
            if key in parsed_data and parsed_data.get(key) not in (None, "", [], {}):
                compact_parsed[key] = self._compact_value(parsed_data.get(key))

        exceptions = parsed_data.get("exceptions")
        if isinstance(exceptions, list) and exceptions:
            first = exceptions[0] if isinstance(exceptions[0], dict) else {}
            compact_parsed["exception_summary"] = {
                "type": str(first.get("type") or ""),
                "message": str(first.get("message") or "")[:180],
            }
        if "urls" in parsed_data and parsed_data.get("urls"):
            compact_parsed["urls"] = self._compact_value(parsed_data.get("urls"))
        if "class_names" in parsed_data and parsed_data.get("class_names"):
            compact_parsed["class_names"] = self._compact_value(parsed_data.get("class_names"))

        if not compact_parsed:
            for key, value in list(parsed_data.items())[:6]:
                if value not in (None, "", [], {}):
                    compact_parsed[str(key)] = self._compact_value(value)

        return {
            "log_excerpt": str(context.get("log_excerpt") or "")[:240],
            "parsed_data": compact_parsed,
            "interface_mapping": {
                "matched": bool(interface_mapping.get("matched")),
                "confidence": interface_mapping.get("confidence"),
                "domain": interface_mapping.get("domain"),
                "aggregate": interface_mapping.get("aggregate"),
                "owner_team": interface_mapping.get("owner_team"),
                "owner": interface_mapping.get("owner"),
                "endpoint": {
                    "method": matched_endpoint.get("method"),
                    "path": matched_endpoint.get("path"),
                    "service": matched_endpoint.get("service"),
                    "interface": matched_endpoint.get("interface"),
                },
                "database_tables": interface_mapping.get("database_tables") or [],
                "code_artifacts": (interface_mapping.get("code_artifacts") or [])[:3],
            },
            "asset_counts": {
                "runtime": int(context.get("runtime_assets_count") or 0),
                "development": int(context.get("dev_assets_count") or 0),
                "design": int(context.get("design_assets_count") or 0),
            },
        }

    def _compact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return value[:140]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            compact_items = [self._compact_value(item) for item in value[:3]]
            return compact_items
        if isinstance(value, dict):
            compact_dict: Dict[str, Any] = {}
            for key, item in list(value.items())[:4]:
                compact_dict[str(key)] = self._compact_value(item)
            return compact_dict
        return str(value)[:140]

    def _to_compact_json(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return "{}"

    def _agent_max_tokens(self, agent_name: str) -> int:
        if agent_name == "JudgeAgent":
            configured = int(settings.DEBATE_JUDGE_MAX_TOKENS)
            return max(800, min(configured, 1400))
        if agent_name in {"CriticAgent", "RebuttalAgent"}:
            configured = int(settings.DEBATE_REVIEW_MAX_TOKENS)
            return max(480, min(configured, 900))
        if agent_name == "ProblemAnalysisAgent":
            configured = int(settings.DEBATE_ANALYSIS_MAX_TOKENS)
            return max(520, min(configured, 900))
        configured = int(settings.DEBATE_ANALYSIS_MAX_TOKENS)
        return max(420, min(configured, 800))

    def _agent_timeout_plan(self, agent_name: str) -> List[float]:
        if agent_name == "JudgeAgent":
            first_timeout = float(max(18, int(settings.llm_judge_timeout)))
            retry_timeout = float(max(first_timeout, int(settings.llm_judge_retry_timeout)))
            return [first_timeout, retry_timeout]
        if agent_name == "ProblemAnalysisAgent":
            first_timeout = float(max(12, int(settings.llm_analysis_timeout)))
            retry_timeout = float(max(first_timeout, min(int(settings.llm_analysis_timeout) + 10, 60)))
            return [first_timeout, retry_timeout]
        if agent_name in {"CriticAgent", "RebuttalAgent"}:
            return [float(max(12, int(settings.llm_review_timeout)))]
        return [float(max(12, int(settings.llm_analysis_timeout)))]

    def _agent_http_timeout(self, agent_name: str) -> int:
        if agent_name == "JudgeAgent":
            return max(20, min(int(settings.llm_judge_retry_timeout), 120))
        if agent_name in {"CriticAgent", "RebuttalAgent"}:
            return max(15, min(int(settings.llm_review_timeout), 90))
        return max(15, min(int(settings.llm_analysis_timeout), 90))

    def _prepare_timeout_retry_input(
        self,
        spec: AgentSpec,
        prompt: str,
        max_tokens: int,
    ) -> tuple[str, int, bool]:
        """超时重试时压缩上下文和输出预算，优先保留首尾关键指令与结构。"""
        original_prompt = str(prompt or "")
        original_tokens = max(128, int(max_tokens or 256))
        if spec.name == "JudgeAgent":
            compact_prompt = self._compact_prompt_for_retry(original_prompt, max_chars=2000)
            compact_tokens = max(520, min(original_tokens, 700))
        elif spec.name == "ProblemAnalysisAgent":
            compact_prompt = self._compact_prompt_for_retry(original_prompt, max_chars=1700)
            compact_tokens = max(360, min(original_tokens, 480))
        else:
            compact_prompt = self._compact_prompt_for_retry(original_prompt, max_chars=1400)
            compact_tokens = max(300, min(original_tokens, 420))
        compacted = (compact_prompt != original_prompt) or (compact_tokens != original_tokens)
        return compact_prompt, compact_tokens, compacted

    def _compact_prompt_for_retry(self, prompt: str, max_chars: int) -> str:
        text = str(prompt or "")
        limit = max(700, int(max_chars))
        if len(text) <= limit:
            return text
        head_len = int(limit * 0.62)
        tail_len = max(120, limit - head_len)
        return (
            f"{text[:head_len]}\n\n"
            "[中间上下文在超时重试时已压缩，保留首尾关键指令、证据和输出格式]\n\n"
            f"{text[-tail_len:]}"
        )

    # Compatibility wrappers: parsing/normalization implementation was moved to
    # app.runtime.langgraph.parsers to keep runtime focused on graph orchestration.
    def _normalize_agent_output(self, agent_name: str, raw_content: str) -> Dict[str, Any]:
        return normalize_agent_output_parser(
            agent_name,
            raw_content,
            judge_fallback_summary=self.JUDGE_FALLBACK_SUMMARY,
        )

    def _normalize_commander_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        return normalize_commander_output_parser(parsed, raw_content)

    def _normalize_normal_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        return normalize_normal_output(parsed, raw_content)

    def _normalize_judge_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        return normalize_judge_output(
            parsed,
            raw_content,
            fallback_summary=self.JUDGE_FALLBACK_SUMMARY,
        )

    def _is_placeholder_summary(self, summary: str) -> bool:
        text = str(summary or "").strip()
        if not text:
            return True
        lowered = text.lower()
        placeholders = {
            self.JUDGE_FALLBACK_SUMMARY,
            "待评估",
            "待确认",
            "unknown",
            "待分析",
        }
        if text in placeholders:
            return True
        if "需要进一步分析" in text:
            return True
        if "further analysis" in lowered:
            return True
        return False

    def _synthesize_final_from_history(self, history_cards: List[AgentEvidence]) -> Optional[Dict[str, Any]]:
        candidates: List[AgentEvidence] = []
        for card in history_cards:
            if card.agent_name == "JudgeAgent":
                continue
            if self._is_placeholder_summary(card.conclusion):
                continue
            if not str(card.conclusion or "").strip():
                continue
            candidates.append(card)
        if not candidates:
            return None

        candidates.sort(key=lambda item: float(item.confidence or 0.0), reverse=True)
        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None

        category_map = {
            "CodeAgent": "code_or_resource",
            "LogAgent": "runtime_log",
            "DomainAgent": "domain_mapping",
            "CriticAgent": "peer_review",
            "RebuttalAgent": "peer_review",
        }
        category = category_map.get(best.agent_name, "multi_agent_inference")
        root_confidence = max(0.55, min(0.95, float(best.confidence or 0.6)))

        evidence_chain: List[Dict[str, Any]] = []
        raw_evidence = best.evidence_chain if isinstance(best.evidence_chain, list) else []
        for item in raw_evidence[:3]:
            text = str(item or "").strip()
            if not text:
                continue
            evidence_chain.append(
                {
                    "type": "analysis",
                    "description": text[:220],
                    "source": best.agent_name,
                    "location": None,
                    "strength": "strong" if root_confidence >= 0.8 else "medium",
                }
            )
        if not evidence_chain:
            evidence_chain.append(
                {
                    "type": "analysis",
                    "description": str(best.summary or best.conclusion)[:220],
                    "source": best.agent_name,
                    "location": None,
                    "strength": "medium",
                }
            )

        key_factors = [f"{best.agent_name}: {str(best.summary or best.conclusion)[:140]}"]
        if second:
            key_factors.append(f"{second.agent_name}: {str(second.summary or second.conclusion)[:140]}")

        return {
            "confidence": root_confidence,
            "final_judgment": {
                "root_cause": {
                    "summary": str(best.conclusion)[:260],
                    "category": category,
                    "confidence": root_confidence,
                },
                "evidence_chain": evidence_chain,
                "fix_recommendation": {
                    "summary": str(best.conclusion)[:260],
                    "steps": [str(best.summary or best.conclusion)[:180]],
                    "code_changes_required": best.agent_name in {"CodeAgent", "RebuttalAgent"},
                    "rollback_recommended": False,
                    "testing_requirements": ["回归故障链路", "压力与超时测试"],
                },
                "impact_analysis": {
                    "affected_services": [],
                    "business_impact": "以实际流量与接口失败率为准",
                    "affected_users": "接口调用用户",
                },
                "risk_assessment": {
                    "risk_level": "high" if root_confidence < 0.75 else "medium",
                    "risk_factors": ["JudgeAgent 超时，采用高置信 Agent 结论合成最终结论"],
                    "mitigation_suggestions": ["补充关键指标后可再次触发全量辩论"],
                },
            },
            "decision_rationale": {
                "key_factors": key_factors,
                "reasoning": "JudgeAgent 未在时限内返回，系统已基于成功 Agent 的高置信结论自动收敛。",
            },
            "action_items": [
                {"priority": 1, "action": str(best.conclusion)[:180], "owner": "待确认"},
            ],
            "responsible_team": {"team": "待确认", "owner": "待确认"},
        }

    def _build_final_payload(
        self,
        history_cards: List[AgentEvidence],
        consensus_reached: bool,
        executed_rounds: int,
    ) -> Dict[str, Any]:
        judge_turn = next((turn for turn in reversed(self.turns) if turn.agent_name == "JudgeAgent"), None)

        if judge_turn:
            output = judge_turn.output_content
            confidence = float(output.get("confidence") or judge_turn.confidence or 0.0)
            final_judgment = output.get("final_judgment") or {}
            decision_rationale = output.get("decision_rationale") or {}
            action_items = output.get("action_items") or []
            responsible_team = output.get("responsible_team") or {}
        else:
            confidence = 0.0
            final_judgment = {
                "root_cause": {
                    "summary": "未生成有效结论",
                    "category": "unknown",
                    "confidence": 0.0,
                },
                "evidence_chain": [],
                "fix_recommendation": {
                    "summary": "请重试分析流程",
                    "steps": [],
                    "code_changes_required": False,
                    "rollback_recommended": False,
                    "testing_requirements": [],
                },
                "impact_analysis": {
                    "affected_services": [],
                    "business_impact": "未知",
                    "affected_users": "未知",
                },
                "risk_assessment": {
                    "risk_level": "medium",
                    "risk_factors": [],
                    "mitigation_suggestions": [],
                },
            }
            decision_rationale = {"key_factors": [], "reasoning": "缺少 Judge 输出"}
            action_items = []
            responsible_team = {"team": "待确认", "owner": "待确认"}

        root_cause = final_judgment.get("root_cause") if isinstance(final_judgment, dict) else {}
        root_summary = ""
        if isinstance(root_cause, dict):
            root_summary = str(root_cause.get("summary") or "").strip()
        if self._is_placeholder_summary(root_summary):
            synthesized = self._synthesize_final_from_history(history_cards)
            if synthesized:
                confidence = float(synthesized.get("confidence") or confidence or 0.0)
                final_judgment = synthesized.get("final_judgment") or final_judgment
                decision_rationale = synthesized.get("decision_rationale") or decision_rationale
                action_items = synthesized.get("action_items") or action_items
                responsible_team = synthesized.get("responsible_team") or responsible_team

        dissenting_opinions = [
            {
                "agent": card.agent_name,
                "phase": card.phase,
                "summary": card.summary,
                "conclusion": card.conclusion,
            }
            for card in history_cards
            if card.agent_name in {"CriticAgent", "RebuttalAgent"}
        ]

        return {
            "confidence": max(0.0, min(1.0, confidence)),
            "consensus_reached": consensus_reached,
            "executed_rounds": max(1, executed_rounds),
            "final_judgment": final_judgment,
            "decision_rationale": decision_rationale,
            "action_items": action_items,
            "responsible_team": responsible_team,
            "dissenting_opinions": dissenting_opinions,
            "debate_history": [
                {
                    "round_number": turn.round_number,
                    "phase": turn.phase,
                    "agent_name": turn.agent_name,
                    "agent_role": turn.agent_role,
                    "model": turn.model,
                    "input_message": turn.input_message,
                    "output_content": turn.output_content,
                    "confidence": turn.confidence,
                    "started_at": turn.started_at.isoformat(),
                    "completed_at": turn.completed_at.isoformat() if turn.completed_at else None,
                }
                for turn in self.turns
            ],
        }

    @staticmethod
    def _base_url_for_llm() -> str:
        base = settings.LLM_BASE_URL.rstrip("/")
        if base.endswith("/v1") or base.endswith("/v3"):
            return base
        return f"{base}/v3"

    def _chat_endpoint(self) -> str:
        base = self._base_url_for_llm()
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    async def _emit_event(self, event: Dict[str, Any]) -> None:
        event_payload = enrich_event(
            event,
            trace_id=self.trace_id or None,
            default_phase=str(event.get("phase") or ""),
        )
        if self.session_id and "session_id" not in event_payload:
            event_payload["session_id"] = self.session_id
        await runtime_session_store.append_event(
            self.session_id or "unknown",
            event_payload,
        )
        if not self._event_callback:
            return
        maybe = self._event_callback(event_payload)
        if asyncio.iscoroutine(maybe):
            await maybe


langgraph_runtime_orchestrator = LangGraphRuntimeOrchestrator(
    consensus_threshold=settings.DEBATE_CONSENSUS_THRESHOLD,
    max_rounds=settings.DEBATE_MAX_ROUNDS,
)
