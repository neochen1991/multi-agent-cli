"""
LangGraph Runtime orchestration for multi-agent, multi-round debate.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict
from uuid import uuid4

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.core.event_schema import enrich_event
from app.core.json_utils import extract_json_dict
from app.core.llm_client import LLMClient
from app.runtime.messages import AgentEvidence, FinalVerdict, RoundCheckpoint
from app.runtime.session_store import runtime_session_store

logger = structlog.get_logger()


class _DebateExecState(TypedDict, total=False):
    context: Dict[str, Any]
    context_summary: Dict[str, Any]
    history_cards: List[AgentEvidence]
    consensus_reached: bool
    executed_rounds: int
    current_round: int
    continue_next_round: bool
    agent_commands: Dict[str, Dict[str, Any]]
    final_payload: Dict[str, Any]


@dataclass
class DebateTurn:
    round_number: int
    phase: str
    agent_name: str
    agent_role: str
    model: Dict[str, str]
    input_message: str
    output_content: Dict[str, Any]
    confidence: float
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    phase: str
    system_prompt: str


class LangGraphRuntimeOrchestrator:
    """LangGraph-backed orchestrator with persisted checkpoints."""

    MAX_HISTORY_ITEMS = 2
    PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent")
    COLLABORATION_PEER_LIMIT = 2
    STREAM_CHUNK_SIZE = 160
    STREAM_MAX_CHUNKS = 16
    JUDGE_FALLBACK_SUMMARY = "需要进一步分析"

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
        graph.add_node("init_session", self._graph_init_session)
        graph.add_node("round_start", self._graph_round_start)
        graph.add_node("analysis_parallel", self._graph_analysis_parallel)
        graph.add_node("analysis_collaboration", self._graph_analysis_collaboration)
        graph.add_node("critic", self._graph_critic)
        graph.add_node("rebuttal", self._graph_rebuttal)
        graph.add_node("judge", self._graph_judge)
        graph.add_node("round_evaluate", self._graph_round_evaluate)
        graph.add_node("finalize", self._graph_finalize)
        graph.add_edge(START, "init_session")
        graph.add_edge("init_session", "round_start")
        graph.add_edge("round_start", "analysis_parallel")
        graph.add_conditional_edges(
            "analysis_parallel",
            self._route_after_analysis_parallel,
            {
                "analysis_collaboration": "analysis_collaboration",
                "critic": "critic",
            },
        )
        graph.add_edge("analysis_collaboration", "critic")
        graph.add_conditional_edges(
            "critic",
            self._route_after_critic,
            {
                "rebuttal": "rebuttal",
                "judge": "judge",
            },
        )
        graph.add_edge("rebuttal", "judge")
        graph.add_edge("judge", "round_evaluate")
        graph.add_conditional_edges(
            "round_evaluate",
            self._route_after_round_evaluate,
            {
                "round_start": "round_start",
                "finalize": "finalize",
            },
        )
        graph.add_edge("finalize", END)
        app = graph.compile()

        try:
            result_state = await app.ainvoke(
                {
                    "context": context,
                    "context_summary": context_summary,
                }
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
            "consensus_reached": False,
            "executed_rounds": 0,
            "current_round": 0,
            "continue_next_round": False,
            "agent_commands": {},
        }

    def _route_after_analysis_parallel(self, state: _DebateExecState) -> str:
        return "analysis_collaboration" if settings.DEBATE_ENABLE_COLLABORATION else "critic"

    def _route_after_critic(self, state: _DebateExecState) -> str:
        return "rebuttal" if settings.DEBATE_ENABLE_CRITIQUE else "judge"

    def _route_after_round_evaluate(self, state: _DebateExecState) -> str:
        return "round_start" if bool(state.get("continue_next_round")) else "finalize"

    async def _graph_round_start(self, state: _DebateExecState) -> _DebateExecState:
        current_round = int(state.get("current_round") or 0) + 1
        if current_round > max(1, self.max_rounds):
            return {"continue_next_round": False}
        history_cards = list(state.get("history_cards") or [])
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
        commands = await self._run_problem_analysis_commander(
            loop_round=current_round,
            compact_context=compact_context,
            history_cards=history_cards,
        )
        self._active_round_commands = commands
        return {
            "current_round": current_round,
            "continue_next_round": False,
            "agent_commands": commands,
        }

    async def _graph_analysis_parallel(self, state: _DebateExecState) -> _DebateExecState:
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        compact_context = self._compact_round_context(context_summary)
        await self._run_parallel_analysis_phase(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
        )
        return {"history_cards": history_cards}

    async def _graph_analysis_collaboration(self, state: _DebateExecState) -> _DebateExecState:
        if not settings.DEBATE_ENABLE_COLLABORATION:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        compact_context = self._compact_round_context(context_summary)
        await self._run_collaboration_phase(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
        )
        return {"history_cards": history_cards}

    async def _graph_critic(self, state: _DebateExecState) -> _DebateExecState:
        if not settings.DEBATE_ENABLE_CRITIQUE:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        compact_context = self._compact_round_context(context_summary)
        await self._run_single_phase_agent(
            agent_name="CriticAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
        )
        return {"history_cards": history_cards}

    async def _graph_rebuttal(self, state: _DebateExecState) -> _DebateExecState:
        if not settings.DEBATE_ENABLE_CRITIQUE:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        compact_context = self._compact_round_context(context_summary)
        await self._run_single_phase_agent(
            agent_name="RebuttalAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
        )
        return {"history_cards": history_cards}

    async def _graph_judge(self, state: _DebateExecState) -> _DebateExecState:
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        compact_context = self._compact_round_context(context_summary)
        await self._run_single_phase_agent(
            agent_name="JudgeAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
        )
        await self._emit_problem_analysis_final_summary(
            loop_round=loop_round,
            history_cards=history_cards,
        )
        return {"history_cards": history_cards}

    async def _graph_round_evaluate(self, state: _DebateExecState) -> _DebateExecState:
        current_round = int(state.get("current_round") or 1)
        history_cards = list(state.get("history_cards") or [])
        judge_turn = self.turns[-1] if self.turns else None
        judge_confidence = float((judge_turn.confidence if judge_turn else 0.0) or 0.0)
        consensus_reached = judge_confidence >= self.consensus_threshold
        executed_rounds = max(int(state.get("executed_rounds") or 0), current_round)
        await self._emit_event(
            {
                "type": "round_completed",
                "loop_round": current_round,
                "consensus_reached": consensus_reached,
                "judge_confidence": judge_confidence,
                "mode": "langgraph_runtime",
            }
        )
        continue_next_round = (
            (not consensus_reached or current_round < self.min_rounds)
            and current_round < max(1, self.max_rounds)
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
        return AgentSpec(
            name="ProblemAnalysisAgent",
            role="问题分析主Agent/调度协调者",
            phase="analysis",
            system_prompt=(
                "你是生产故障问题分析主Agent。你负责拆解问题、向各专家Agent下达命令，并收敛最终结论。"
                "请输出紧凑 JSON。"
            ),
        )

    def _coordinator_command_schema(self) -> Dict[str, Any]:
        return {
            "chat_message": "",
            "analysis": "",
            "conclusion": "",
            "commands": [
                {
                    "target_agent": "LogAgent|DomainAgent|CodeAgent|CriticAgent|RebuttalAgent|JudgeAgent",
                    "task": "",
                    "focus": "",
                    "expected_output": "",
                }
            ],
            "evidence_chain": [""],
            "confidence": 0.0,
        }

    def _build_problem_analysis_commander_prompt(
        self,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
    ) -> str:
        peer_items = [
            {
                "agent": card.agent_name,
                "phase": card.phase,
                "summary": card.summary[:100],
                "conclusion": card.conclusion[:120],
                "confidence": round(float(card.confidence or 0.0), 3),
            }
            for card in history_cards[-6:]
        ]
        schema = self._coordinator_command_schema()
        return (
            f"你是问题分析主Agent。当前第 {loop_round}/{self.max_rounds} 轮。\n"
            "请先给出一段简短会议发言(chat_message)，然后给出对各专家Agent的命令清单(commands)。\n"
            "必须覆盖 LogAgent、DomainAgent、CodeAgent；若已存在历史结论，可补充 CriticAgent/RebuttalAgent/JudgeAgent 命令。\n"
            "命令要具体到分析重点，不要泛泛而谈。\n\n"
            f"故障上下文:\n```json\n{self._to_compact_json(context)}\n```\n\n"
            f"已有观点卡片:\n```json\n{self._to_compact_json(peer_items)}\n```\n\n"
            f"仅输出 JSON，格式:\n```json\n{self._to_compact_json(schema)}\n```"
        )

    async def _run_problem_analysis_commander(
        self,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
    ) -> Dict[str, Dict[str, Any]]:
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
        )
        try:
            turn = await self._call_agent(
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
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

        raw_commands = turn.output_content.get("commands")
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
        # 保底命令，避免主Agent未返回结构化命令时执行链路中断
        defaults = {
            "LogAgent": "分析错误日志、502 与 CPU 异常的直接证据链",
            "DomainAgent": "根据接口 URL 映射领域/聚合根/责任田并确认负责团队",
            "CodeAgent": "定位可能代码瓶颈、连接池/线程池/慢SQL风险点",
            "CriticAgent": "质疑前述结论中的证据缺口和假设跳跃",
            "RebuttalAgent": "针对质疑补充证据并收敛执行建议",
            "JudgeAgent": "综合所有结论给出最终根因裁决与处置建议",
        }
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
        return commands

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
                self._call_agent(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
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
                self._call_agent(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
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

    async def _run_single_phase_agent(
        self,
        agent_name: str,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        agent_commands: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        spec = self._spec_by_name(agent_name)
        if not spec:
            return
        round_number = len(self.turns) + 1
        assigned_command = (agent_commands or {}).get(agent_name)
        if assigned_command:
            await self._emit_agent_command_issued(
                commander="ProblemAnalysisAgent",
                target=agent_name,
                loop_round=loop_round,
                round_number=round_number,
                command=assigned_command,
            )
        prompt = self._build_peer_driven_prompt(
            spec=spec,
            loop_round=loop_round,
            context=compact_context,
            history_cards=history_cards,
            assigned_command=assigned_command,
        )
        try:
            turn = await self._call_agent(
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
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
        if assigned_command:
            await self._emit_agent_command_feedback(
                source=agent_name,
                loop_round=loop_round,
                round_number=round_number,
                command=assigned_command,
                turn=turn,
            )

    async def _graph_debate_loop(self, state: _DebateExecState) -> _DebateExecState:
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        consensus_reached = bool(state.get("consensus_reached") or False)
        executed_rounds = int(state.get("executed_rounds") or 0)

        for loop_round in range(1, max(1, self.max_rounds) + 1):
            executed_rounds = loop_round
            await self._emit_event(
                {
                    "type": "round_started",
                    "loop_round": loop_round,
                    "max_rounds": self.max_rounds,
                    "mode": "langgraph_runtime",
                }
            )

            round_turns = await self._execute_groupchat_round(
                loop_round=loop_round,
                context=context_summary,
                history_cards=history_cards,
            )
            if not round_turns:
                raise RuntimeError(f"第 {loop_round} 轮未产生有效 Agent 输出")

            judge_turn = self.turns[-1] if self.turns else None
            judge_confidence = float((judge_turn.confidence if judge_turn else 0.0) or 0.0)
            consensus_reached = judge_confidence >= self.consensus_threshold
            await self._emit_event(
                {
                    "type": "round_completed",
                    "loop_round": loop_round,
                    "consensus_reached": consensus_reached,
                    "judge_confidence": judge_confidence,
                    "mode": "langgraph_runtime",
                }
            )
            if consensus_reached and loop_round >= self.min_rounds:
                break

        final_payload = self._build_final_payload(
            history_cards=history_cards,
            consensus_reached=consensus_reached,
            executed_rounds=executed_rounds,
        )
        return {
            "history_cards": history_cards,
            "consensus_reached": consensus_reached,
            "executed_rounds": executed_rounds,
            "final_payload": final_payload,
        }

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

    async def _execute_groupchat_round(
        self,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
    ) -> List[DebateTurn]:
        sequence = self._agent_sequence()
        if not sequence:
            return []

        turns: List[DebateTurn] = []
        compact_context = self._compact_round_context(context)
        base_round_number = len(self.turns) + 1
        parallel_names = set(self.PARALLEL_ANALYSIS_AGENTS)
        parallel_specs = [
            spec
            for spec in sequence
            if spec.phase == "analysis" and spec.name in parallel_names
        ]
        sequential_specs = [
            spec
            for spec in sequence
            if spec not in parallel_specs
        ]

        round_cursor = base_round_number

        if parallel_specs:
            parallel_history = list(history_cards)
            parallel_inputs: List[tuple[AgentSpec, int, str]] = []
            for spec in parallel_specs:
                round_number = round_cursor
                round_cursor += 1
                prompt = self._build_agent_prompt(
                    spec=spec,
                    loop_round=loop_round,
                    context=compact_context,
                    history_cards=parallel_history,
                )
                parallel_inputs.append((spec, round_number, prompt))

            await self._emit_event(
                {
                    "type": "parallel_analysis_started",
                    "phase": "analysis",
                    "loop_round": loop_round,
                    "session_id": self.session_id,
                    "agents": [spec.name for spec, _, _ in parallel_inputs],
                }
            )

            parallel_tasks = [
                asyncio.create_task(
                    self._call_agent(
                        spec=spec,
                        prompt=prompt,
                        round_number=round_number,
                        loop_round=loop_round,
                    )
                )
                for spec, round_number, prompt in parallel_inputs
            ]
            parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

            for (spec, round_number, prompt), result in zip(parallel_inputs, parallel_results):
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
                turns.append(turn)
                await self._record_turn(
                    turn=turn,
                    loop_round=loop_round,
                    history_cards=history_cards,
                )

            await self._emit_event(
                {
                    "type": "parallel_analysis_completed",
                    "phase": "analysis",
                    "loop_round": loop_round,
                    "session_id": self.session_id,
                    "agents": [spec.name for spec, _, _ in parallel_inputs],
                }
            )

            # 协同复核会显著增加 1 轮三并发调用，默认关闭；可通过配置开启。
            if settings.DEBATE_ENABLE_COLLABORATION:
                peer_cards = self._latest_cards_for_agents(
                    history_cards=history_cards,
                    agent_names=[spec.name for spec in parallel_specs],
                    limit=self.COLLABORATION_PEER_LIMIT,
                )
                collab_inputs: List[tuple[AgentSpec, int, str]] = []
                for spec in parallel_specs:
                    round_number = round_cursor
                    round_cursor += 1
                    prompt = self._build_collaboration_prompt(
                        spec=spec,
                        loop_round=loop_round,
                        context=compact_context,
                        peer_cards=peer_cards,
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
                        self._call_agent(
                            spec=spec,
                            prompt=prompt,
                            round_number=round_number,
                            loop_round=loop_round,
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
                    turns.append(turn)
                    await self._record_turn(
                        turn=turn,
                        loop_round=loop_round,
                        history_cards=history_cards,
                    )

                await self._emit_event(
                    {
                        "type": "parallel_analysis_collaboration_completed",
                        "phase": "analysis",
                        "loop_round": loop_round,
                        "session_id": self.session_id,
                        "agents": [spec.name for spec, _, _ in collab_inputs],
                    }
                )

        for spec in sequential_specs:
            round_number = round_cursor
            round_cursor += 1
            prompt = self._build_peer_driven_prompt(
                spec=spec,
                loop_round=loop_round,
                context=compact_context,
                history_cards=history_cards,
            )
            try:
                turn = await self._call_agent(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
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
            turns.append(turn)
            await self._record_turn(
                turn=turn,
                loop_round=loop_round,
                history_cards=history_cards,
            )

        return turns

    def _build_peer_driven_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
    ) -> str:
        peer_items = self._collect_peer_items(
            history_cards=history_cards,
            exclude_agent=spec.name,
            limit=max(2, self.MAX_HISTORY_ITEMS + 1),
        )
        if spec.name == "JudgeAgent":
            output_schema = self._judge_output_schema()
            command_block = ""
            if assigned_command:
                command_block = (
                    f"\n主Agent命令：\n```json\n{self._to_compact_json(assigned_command)}\n```\n"
                    "你必须响应主Agent命令要求并在 chat_message 中体现“已收到命令/正在综合裁决”。\n"
                )
            return (
                f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{self.max_rounds} 轮，阶段={spec.phase}。\n"
                "必须基于其他 Agent 结论进行综合裁决，禁止独立发挥。\n"
                "请用真人开会讨论的口吻在 chat_message 中表达观点（简短、明确引用同伴结论），并输出 JSON。\n"
                "字段尽量精炼，action_items 最多 3 条。\n\n"
                f"{command_block}"
                f"故障上下文：\n```json\n{self._to_compact_json(context)}\n```\n\n"
                f"同伴结论：\n```json\n{self._to_compact_json(peer_items)}\n```\n\n"
                f"输出格式：\n```json\n{self._to_compact_json(output_schema)}\n```"
            )

        output_schema = {
            "chat_message": "",
            "analysis": "",
            "conclusion": "",
            "evidence_chain": [""],
            "confidence": 0.0,
        }
        command_block = ""
        if assigned_command:
            command_block = (
                f"\n主Agent命令：\n```json\n{self._to_compact_json(assigned_command)}\n```\n"
                "你必须先在 chat_message 中确认收到主Agent命令，再给出执行结果。\n"
            )
        return (
            f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{self.max_rounds} 轮，阶段={spec.phase}。\n"
            "必须基于其他 Agent 的结论进行分析，禁止独立分析。\n"
            "请以真人讨论口吻在 chat_message 中先说结论（1-3句），再给结构化字段。\n"
            "要求：\n"
            "1) 至少明确采纳/反驳 1 条同伴结论；\n"
            "2) evidence_chain 至少包含 1 条 peer:<agent_name>:<观点>；\n"
            "3) 仅输出 JSON，内容尽量简短。\n\n"
            f"{command_block}"
            f"故障上下文：\n```json\n{self._to_compact_json(context)}\n```\n\n"
            f"同伴结论：\n```json\n{self._to_compact_json(peer_items)}\n```\n\n"
            f"输出格式：\n```json\n{self._to_compact_json(output_schema)}\n```"
        )

    def _judge_output_schema(self) -> Dict[str, Any]:
        return {
            "chat_message": "",
            "final_judgment": {
                "root_cause": {"summary": "", "category": "", "confidence": 0.0},
                "evidence_chain": [
                    {
                        "type": "log|code|domain|metrics",
                        "description": "",
                        "source": "",
                        "location": "",
                        "strength": "strong|medium|weak",
                    }
                ],
                "fix_recommendation": {
                    "summary": "",
                    "steps": [],
                    "code_changes_required": True,
                },
                "impact_analysis": {
                    "affected_services": [],
                    "business_impact": "",
                },
                "risk_assessment": {
                    "risk_level": "critical|high|medium|low",
                    "risk_factors": [],
                },
            },
            "decision_rationale": {"key_factors": [], "reasoning": ""},
            "action_items": [],
            "responsible_team": {"team": "", "owner": ""},
            "confidence": 0.0,
        }

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
            self._normalize_judge_output({}, f"{spec.name} {friendly_reason}")
            if spec.name == "JudgeAgent"
            else self._normalize_normal_output(
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
        sequence = [
            AgentSpec(
                name="LogAgent",
                role="日志分析专家",
                phase="analysis",
                system_prompt=(
                    "你是生产故障日志分析专家。只输出紧凑 JSON。"
                    "聚焦异常模式、调用链、资源指标与关键证据。"
                ),
            ),
            AgentSpec(
                name="DomainAgent",
                role="领域映射专家",
                phase="analysis",
                system_prompt=(
                    "你是 DDD 领域映射专家。只输出紧凑 JSON。"
                    "必须将接口现象映射到 domain/aggregate/responsibility。"
                ),
            ),
            AgentSpec(
                name="CodeAgent",
                role="代码分析专家",
                phase="analysis",
                system_prompt=(
                    "你是代码根因分析专家。只输出紧凑 JSON。"
                    "给出最可能代码位置、触发条件和修复建议。"
                ),
            ),
        ]
        if settings.DEBATE_ENABLE_CRITIQUE:
            sequence.extend(
                [
                    AgentSpec(
                        name="CriticAgent",
                        role="架构质疑专家",
                        phase="critique",
                        system_prompt=(
                            "你是技术评审质疑专家。只输出紧凑 JSON。"
                            "找出前面结论中的漏洞和不充分证据。"
                        ),
                    ),
                    AgentSpec(
                        name="RebuttalAgent",
                        role="技术反驳专家",
                        phase="rebuttal",
                        system_prompt=(
                            "你是技术反驳专家。只输出紧凑 JSON。"
                            "针对质疑补充证据，收敛到可执行结论。"
                        ),
                    ),
                ]
            )

        sequence.append(
            AgentSpec(
                name="JudgeAgent",
                role="技术委员会主席",
                phase="judgment",
                system_prompt=(
                    "你是技术委员会主席。基于证据给出最终裁决。"
                    "必须只输出 JSON，字段严格包含 final_judgment 与 confidence。"
                ),
            )
        )
        return sequence

    def _build_agent_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
    ) -> str:
        history_items = [
            {
                "agent": card.agent_name,
                "phase": card.phase,
                "summary": card.summary[:120],
                "conclusion": card.conclusion[:140],
                "evidence": card.evidence_chain[:2],
                "confidence": round(float(card.confidence), 3),
            }
            for card in history_cards[-self.MAX_HISTORY_ITEMS :]
        ]

        if spec.name == "JudgeAgent":
            output_schema = self._judge_output_schema()
        else:
            output_schema = {
                "chat_message": "",
                "analysis": "",
                "conclusion": "",
                "evidence_chain": [""],
                "confidence": 0.0,
            }

        output_constraints = ""
        if spec.name == "JudgeAgent":
            output_constraints = "action_items 最多 3 条，decision_rationale.reasoning 控制在 120 字内。\n\n"

        command_block = ""
        if assigned_command:
            command_block = (
                f"主Agent命令：\n```json\n{self._to_compact_json(assigned_command)}\n```\n"
                "必须在 chat_message 中先确认收到命令，并围绕命令重点输出。\n\n"
            )
        return (
            f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{self.max_rounds} 轮，阶段={spec.phase}。\n"
            "只需要基于核心观点与结论推理，不要复述全部历史，结论请简短。\n"
            "请以真人讨论口吻在 chat_message 中表达你的发言（1-3句），然后输出 JSON。\n\n"
            f"{output_constraints}"
            f"{command_block}"
            f"故障上下文：\n```json\n{self._to_compact_json(context)}\n```\n\n"
            f"最近结论卡片：\n```json\n{self._to_compact_json(history_items)}\n```\n\n"
            f"请仅输出 JSON，格式示例：\n```json\n{self._to_compact_json(output_schema)}\n```"
        )

    def _build_collaboration_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        peer_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
    ) -> str:
        peer_items = [
            {
                "agent": card.agent_name,
                "summary": card.summary[:120],
                "conclusion": card.conclusion[:160],
                "confidence": round(float(card.confidence), 3),
            }
            for card in peer_cards
            if card.agent_name != spec.name
        ]
        output_schema = {
            "chat_message": "",
            "analysis": "",
            "conclusion": "",
            "evidence_chain": [""],
            "confidence": 0.0,
        }
        command_block = ""
        if assigned_command:
            command_block = (
                f"\n主Agent命令：\n```json\n{self._to_compact_json(assigned_command)}\n```\n"
                "你需要在 chat_message 中明确这是对主Agent命令的执行反馈。\n"
            )
        return (
            f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{self.max_rounds} 轮，阶段=analysis。\n"
            "现在进入协同复核阶段：你必须基于其他 Agent 的结论进行交叉校验并修正自己的判断。\n"
            "请以真人讨论口吻在 chat_message 中明确你在回应谁、采纳或反驳什么。\n"
            "要求：\n"
            "1) 明确指出至少 1 条你采纳或反驳的同伴结论；\n"
            "2) 在 evidence_chain 中包含同伴观点依据（可写成 peer:<agent_name>:<观点>）；\n"
            "3) 仅输出 JSON，不要解释文本，保持精炼。\n\n"
            f"{command_block}"
            f"故障上下文：\n```json\n{self._to_compact_json(context)}\n```\n\n"
            f"同伴结论：\n```json\n{self._to_compact_json(peer_items)}\n```\n\n"
            f"输出格式：\n```json\n{self._to_compact_json(output_schema)}\n```"
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

    def _build_groupchat_prompt(
        self,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        sequence: List[AgentSpec],
    ) -> str:
        history_items = [
            {
                "agent": card.agent_name,
                "phase": card.phase,
                "summary": card.summary[:180],
                "conclusion": card.conclusion[:220],
                "confidence": round(float(card.confidence), 3),
            }
            for card in history_cards[-self.MAX_HISTORY_ITEMS :]
        ]
        speaker_order = [spec.name for spec in sequence]
        return (
            f"当前为第 {loop_round}/{self.max_rounds} 轮多Agent技术评审。\n"
            f"必须按顺序发言：{', '.join(speaker_order)}。\n"
            "除了 JudgeAgent 外，其他 Agent 必须仅输出 JSON："
            '{"analysis":"","conclusion":"","evidence_chain":[],"confidence":0.0}。\n'
            "JudgeAgent 必须仅输出 JSON，字段必须包含："
            '{"final_judgment":{},"decision_rationale":{},"action_items":[],"responsible_team":{},"confidence":0.0}。\n'
            "不要输出 markdown，不要输出解释文字。\n\n"
            f"故障上下文：\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```\n\n"
            f"最近核心观点：\n```json\n{json.dumps(history_items, ensure_ascii=False, indent=2)}\n```"
        )

    def _run_groupchat_round(
        self,
        sequence: List[AgentSpec],
        kickoff_prompt: str,
    ) -> List[Dict[str, Any]]:
        # Legacy helper retained for compatibility but no longer used after LangGraph migration.
        _ = sequence
        _ = kickoff_prompt
        raise NotImplementedError("Legacy LangGraph GroupChat path has been replaced by LangGraph runtime")

    async def _call_agent(
        self,
        spec: AgentSpec,
        prompt: str,
        round_number: int,
        loop_round: int,
    ) -> DebateTurn:
        started_at = datetime.utcnow()
        model_name = settings.llm_model
        endpoint = self._chat_endpoint()
        agent_max_tokens = self._agent_max_tokens(spec.name)
        attempt_prompt = prompt
        attempt_max_tokens = agent_max_tokens

        await self._emit_event(
            {
                "type": "llm_call_started",
                "phase": spec.phase,
                "agent_name": spec.name,
                "model": model_name,
                "session_id": self.session_id,
                "loop_round": loop_round,
                "round_number": round_number,
                "prompt_preview": prompt[:1200],
            }
        )
        await self._emit_event(
            {
                "type": "llm_http_request",
                "phase": spec.phase,
                "agent_name": spec.name,
                "session_id": self.session_id,
                "model": model_name,
                "endpoint": endpoint,
                "request_payload": {
                    "model": model_name,
                    "max_tokens": agent_max_tokens,
                    "message_count": 2,
                    "prompt_length": len(prompt),
                    "prompt_preview": prompt[:1200],
                },
            }
        )

        timeout_plan = self._agent_timeout_plan(spec.name)
        logger.info(
            "runtime_agent_llm_scheduled",
            session_id=self.session_id,
            agent_name=spec.name,
            phase=spec.phase,
            loop_round=loop_round,
            round_number=round_number,
            timeout_plan=timeout_plan,
            max_tokens=attempt_max_tokens,
            prompt_length=len(attempt_prompt),
        )

        last_exc: Optional[Exception] = None
        for attempt_idx, attempt_timeout in enumerate(timeout_plan, start=1):
            started_clock = perf_counter()
            try:
                queue_started = perf_counter()
                async with self._llm_semaphore:
                    queue_wait_ms = round((perf_counter() - queue_started) * 1000, 2)
                    logger.info(
                        "runtime_agent_llm_started",
                        session_id=self.session_id,
                        agent_name=spec.name,
                        phase=spec.phase,
                        loop_round=loop_round,
                        round_number=round_number,
                        attempt=attempt_idx,
                        max_attempts=len(timeout_plan),
                        timeout_seconds=attempt_timeout,
                        queue_wait_ms=queue_wait_ms,
                    )
                    raw_content = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._run_agent_once,
                            spec,
                            attempt_prompt,
                            attempt_max_tokens,
                        ),
                        timeout=attempt_timeout,
                    )
                latency_ms = round((perf_counter() - started_clock) * 1000, 2)
                payload = self._normalize_agent_output(spec.name, raw_content)
                if spec.name == "JudgeAgent":
                    final_judgment = payload.get("final_judgment")
                    root_cause = final_judgment.get("root_cause") if isinstance(final_judgment, dict) else {}
                    root_summary = (
                        str(root_cause.get("summary") or "").strip()
                        if isinstance(root_cause, dict)
                        else ""
                    )
                    if root_summary == self.JUDGE_FALLBACK_SUMMARY:
                        await self._emit_event(
                            {
                                "type": "judge_output_fallback_applied",
                                "phase": spec.phase,
                                "agent_name": spec.name,
                                "session_id": self.session_id,
                                "model": model_name,
                                "reason": "judge_output_parse_incomplete",
                                "raw_preview": raw_content[:800],
                            }
                        )
                await self._emit_stream_deltas(
                    spec=spec,
                    raw_content=raw_content,
                    loop_round=loop_round,
                    round_number=round_number,
                )

                completed_at = datetime.utcnow()
                turn = DebateTurn(
                    round_number=round_number,
                    phase=spec.phase,
                    agent_name=spec.name,
                    agent_role=spec.role,
                    model={"name": model_name},
                    input_message=attempt_prompt,
                    output_content=payload,
                    confidence=float(payload.get("confidence", 0.0) or 0.0),
                    started_at=started_at,
                    completed_at=completed_at,
                )

                await self._emit_event(
                    {
                        "type": "llm_http_response",
                        "phase": spec.phase,
                        "agent_name": spec.name,
                        "session_id": self.session_id,
                        "model": model_name,
                        "endpoint": endpoint,
                        "status_code": 200,
                        "response_payload": {
                            "content_preview": raw_content[:1200],
                            "content_length": len(raw_content),
                        },
                        "latency_ms": latency_ms,
                    }
                )
                await self._emit_event(
                    {
                        "type": "agent_round",
                        "phase": spec.phase,
                        "agent_name": spec.name,
                        "agent_role": spec.role,
                        "loop_round": loop_round,
                        "round_number": round_number,
                        "confidence": turn.confidence,
                        "latency_ms": latency_ms,
                        "output_preview": str(payload)[:1200],
                        "output_json": payload,
                        "started_at": started_at.isoformat(),
                        "completed_at": completed_at.isoformat(),
                        "session_id": self.session_id,
                    }
                )
                chat_message = str(payload.get("chat_message") or "").strip()
                if chat_message:
                    await self._emit_event(
                        {
                            "type": "agent_chat_message",
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "agent_role": spec.role,
                            "model": model_name,
                            "session_id": self.session_id,
                            "loop_round": loop_round,
                            "round_number": round_number,
                            "message": chat_message[:1200],
                            "confidence": turn.confidence,
                            "conclusion": str(payload.get("conclusion") or "")[:220],
                            "reply_to": self._infer_reply_target(
                                spec_name=spec.name,
                                history_cards=[c for c in self._history_cards_snapshot() if c.agent_name != spec.name],
                            ),
                        }
                    )
                await self._emit_event(
                    {
                        "type": "llm_call_completed",
                        "phase": spec.phase,
                        "agent_name": spec.name,
                        "model": model_name,
                        "session_id": self.session_id,
                        "response_preview": raw_content[:1200],
                        "latency_ms": latency_ms,
                    }
                )
                logger.info(
                    "runtime_agent_llm_completed",
                    session_id=self.session_id,
                    agent_name=spec.name,
                    phase=spec.phase,
                    loop_round=loop_round,
                    round_number=round_number,
                    attempt=attempt_idx,
                    latency_ms=latency_ms,
                    response_length=len(raw_content or ""),
                    confidence=float(payload.get("confidence", 0.0) or 0.0),
                )
                return turn
            except Exception as exc:
                last_exc = exc
                latency_ms = round((perf_counter() - started_clock) * 1000, 2)
                error_text = str(exc).strip() or exc.__class__.__name__
                is_timeout = isinstance(exc, asyncio.TimeoutError) or "timeout" in error_text.lower()
                if settings.LLM_FAILFAST_ON_RATE_LIMIT and self._is_rate_limited_error(error_text):
                    error_text = f"LLM_RATE_LIMITED: {error_text}"
                retryable = attempt_idx < len(timeout_plan) and (
                    is_timeout
                )
                if retryable:
                    logger.warning(
                        "runtime_agent_llm_retry",
                        session_id=self.session_id,
                        agent_name=spec.name,
                        phase=spec.phase,
                        loop_round=loop_round,
                        round_number=round_number,
                        attempt=attempt_idx,
                        max_attempts=len(timeout_plan),
                        timeout_seconds=attempt_timeout,
                        latency_ms=latency_ms,
                        error=error_text,
                        retry_compacted=(attempt_prompt != prompt),
                    )
                    next_prompt, next_max_tokens, compacted = self._prepare_timeout_retry_input(
                        spec=spec,
                        prompt=attempt_prompt,
                        max_tokens=attempt_max_tokens,
                    )
                    await self._emit_event(
                        {
                            "type": "llm_call_retry",
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "model": model_name,
                            "session_id": self.session_id,
                            "attempt": attempt_idx + 1,
                            "max_attempts": len(timeout_plan),
                            "reason": error_text,
                            "latency_ms": latency_ms,
                            "retry_compacted": compacted,
                        }
                    )
                    attempt_prompt = next_prompt
                    attempt_max_tokens = next_max_tokens
                    if compacted:
                        logger.info(
                            "runtime_agent_llm_retry_compacted",
                            session_id=self.session_id,
                            agent_name=spec.name,
                            phase=spec.phase,
                            loop_round=loop_round,
                            round_number=round_number,
                            next_prompt_length=len(attempt_prompt),
                            next_max_tokens=attempt_max_tokens,
                        )
                        await self._emit_event(
                            {
                                "type": "llm_call_retry_compacted",
                                "phase": spec.phase,
                                "agent_name": spec.name,
                                "model": model_name,
                                "session_id": self.session_id,
                                "next_prompt_length": len(attempt_prompt),
                                "next_max_tokens": attempt_max_tokens,
                            }
                        )
                    continue

                (logger.warning if is_timeout else logger.error)(
                    "runtime_agent_llm_timeout" if is_timeout else "runtime_agent_llm_failed",
                    session_id=self.session_id,
                    agent_name=spec.name,
                    phase=spec.phase,
                    loop_round=loop_round,
                    round_number=round_number,
                    attempt=attempt_idx,
                    max_attempts=len(timeout_plan),
                    timeout_seconds=attempt_timeout,
                    latency_ms=latency_ms,
                    error=error_text,
                )
                await self._emit_event(
                    {
                        "type": "llm_http_error",
                        "phase": spec.phase,
                        "agent_name": spec.name,
                        "session_id": self.session_id,
                        "model": model_name,
                        "endpoint": endpoint,
                        "error": error_text,
                        "latency_ms": latency_ms,
                    }
                )
                await self._emit_event(
                    {
                        "type": "llm_call_timeout" if is_timeout else "llm_call_failed",
                        "phase": spec.phase,
                        "agent_name": spec.name,
                        "model": model_name,
                        "session_id": self.session_id,
                        "error": error_text,
                        "latency_ms": latency_ms,
                        "prompt_preview": attempt_prompt[:1200],
                    }
                )
                raise RuntimeError(f"{spec.name} 调用失败: {error_text}") from exc

        error_text = str(last_exc).strip() if last_exc else "unknown"
        raise RuntimeError(f"{spec.name} 调用失败: {error_text}")

    async def _emit_stream_deltas(
        self,
        spec: AgentSpec,
        raw_content: str,
        loop_round: int,
        round_number: int,
    ) -> None:
        content = (raw_content or "").strip()
        if not content:
            return
        chunks = [
            content[i : i + self.STREAM_CHUNK_SIZE]
            for i in range(0, len(content), self.STREAM_CHUNK_SIZE)
        ]
        truncated = False
        if len(chunks) > self.STREAM_MAX_CHUNKS:
            chunks = chunks[: self.STREAM_MAX_CHUNKS]
            truncated = True
        stream_id = f"{self.session_id}:{spec.name}:{round_number}"
        for index, chunk in enumerate(chunks, start=1):
            await self._emit_event(
                {
                    "type": "llm_stream_delta",
                    "phase": spec.phase,
                    "agent_name": spec.name,
                    "model": settings.llm_model,
                    "session_id": self.session_id,
                    "stream_id": stream_id,
                    "loop_round": loop_round,
                    "round_number": round_number,
                    "chunk_index": index,
                    "chunk_total": len(chunks),
                    "delta": chunk,
                    "truncated": truncated,
                }
            )

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

    def _run_agent_once(self, spec: AgentSpec, prompt: str, max_tokens: int) -> str:
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY 未配置，无法调用模型")
        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.LLM_API_KEY,
            base_url=self._base_url_for_llm(),
            temperature=0.15,
            timeout=self._agent_http_timeout(spec.name),
            max_retries=max(0, int(settings.LLM_MAX_RETRIES)),
            max_tokens=max(128, int(max_tokens or 256)),
            model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
        )
        reply = llm.invoke(
            [
                SystemMessage(content=spec.system_prompt or "你是严谨的 SRE 分析助手。"),
                HumanMessage(content=prompt),
            ]
        )
        return LLMClient._extract_reply_text(reply, agent_name=spec.name)

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

    def _extract_balanced_object(
        self,
        text: str,
        start_index: int,
    ) -> Optional[str]:
        if start_index < 0 or start_index >= len(text) or text[start_index] != "{":
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start_index, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start_index : i + 1]
        return None

    def _extract_object_by_named_key(
        self,
        text: str,
        key_name: str,
    ) -> Optional[Dict[str, Any]]:
        marker = f'"{key_name}"'
        search_start = 0
        while True:
            key_index = text.find(marker, search_start)
            if key_index < 0:
                return None
            colon_index = text.find(":", key_index + len(marker))
            if colon_index < 0:
                return None
            brace_index = text.find("{", colon_index + 1)
            if brace_index < 0:
                return None
            candidate_text = self._extract_balanced_object(text, brace_index)
            search_start = key_index + len(marker)
            if not candidate_text:
                continue
            try:
                parsed = json.loads(candidate_text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    def _extract_top_level_json_with_key(
        self,
        text: str,
        required_key: str,
    ) -> Optional[Dict[str, Any]]:
        matched_payload: Optional[Dict[str, Any]] = None
        matched_length = 0
        marker = f'"{required_key}"'
        for start, ch in enumerate(text):
            if ch != "{":
                continue
            candidate_text = self._extract_balanced_object(text, start)
            if not candidate_text or marker not in candidate_text:
                continue
            try:
                parsed = json.loads(candidate_text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and required_key in parsed and len(candidate_text) > matched_length:
                matched_payload = parsed
                matched_length = len(candidate_text)
        return matched_payload

    def _extract_confidence_hint(self, text: str, fallback: float = 0.5) -> float:
        matches = re.findall(r'"confidence"\s*:\s*(-?\d+(?:\.\d+)?)', text)
        if not matches:
            return fallback
        try:
            value = float(matches[-1])
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, value))

    def _extract_largest_json_dict(self, text: str) -> Dict[str, Any]:
        raw = str(text or "")
        if not raw.strip():
            return {}
        best: Dict[str, Any] = {}
        best_len = 0
        for start, ch in enumerate(raw):
            if ch != "{":
                continue
            candidate = self._extract_balanced_object(raw, start)
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and len(candidate) > best_len:
                best = parsed
                best_len = len(candidate)
        return best

    def _extract_mixed_json_dict(self, raw_content: str) -> Dict[str, Any]:
        raw_text = str(raw_content or "")
        parsed = extract_json_dict(raw_text) or {}
        if isinstance(parsed, dict) and parsed:
            return parsed
        for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw_text, flags=re.IGNORECASE):
            parsed = extract_json_dict(block) or {}
            if isinstance(parsed, dict) and parsed:
                return parsed
            parsed = self._extract_largest_json_dict(block)
            if parsed:
                return parsed
        return self._extract_largest_json_dict(raw_text)

    def _parse_judge_payload(self, raw_content: str) -> Dict[str, Any]:
        raw_text = str(raw_content or "")
        if not raw_text.strip():
            return {}

        # 优先提取包含 final_judgment 的完整对象，避免命中嵌套对象导致结构丢失。
        top_level_payload = self._extract_top_level_json_with_key(raw_text, "final_judgment")
        if isinstance(top_level_payload, dict):
            return top_level_payload

        final_judgment = self._extract_object_by_named_key(raw_text, "final_judgment")
        if isinstance(final_judgment, dict) and final_judgment:
            root_cause_hint = final_judgment.get("root_cause")
            root_confidence = 0.5
            if isinstance(root_cause_hint, dict):
                try:
                    root_confidence = float(root_cause_hint.get("confidence") or 0.5)
                except (TypeError, ValueError):
                    root_confidence = 0.5
            return {
                "final_judgment": final_judgment,
                "confidence": self._extract_confidence_hint(
                    raw_text,
                    fallback=root_confidence,
                ),
            }

        generic_payload = extract_json_dict(raw_text) or {}
        if isinstance(generic_payload, dict) and "final_judgment" in generic_payload:
            return generic_payload

        # 如果解析到的是 final_judgment 内层对象，做一次包装，尽量保留有效结论。
        if isinstance(generic_payload, dict) and any(
            k in generic_payload for k in ("root_cause", "evidence_chain", "fix_recommendation")
        ):
            return {
                "final_judgment": generic_payload,
                "confidence": self._extract_confidence_hint(raw_text, fallback=0.5),
            }

        return generic_payload if isinstance(generic_payload, dict) else {}

    def _normalize_agent_output(self, agent_name: str, raw_content: str) -> Dict[str, Any]:
        if agent_name == "JudgeAgent":
            parsed = self._parse_judge_payload(raw_content)
            normalized = self._normalize_judge_output(parsed, raw_content)
        elif agent_name == "ProblemAnalysisAgent":
            parsed = self._extract_mixed_json_dict(raw_content)
            normalized = self._normalize_commander_output(parsed, raw_content)
        else:
            parsed = self._extract_mixed_json_dict(raw_content)
            normalized = self._normalize_normal_output(parsed, raw_content)
        return normalized

    def _normalize_commander_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        normalized = self._normalize_normal_output(parsed, raw_content)
        commands_raw = parsed.get("commands")
        commands: List[Dict[str, Any]] = []
        if isinstance(commands_raw, list):
            for item in commands_raw[:10]:
                if not isinstance(item, dict):
                    continue
                target_agent = str(item.get("target_agent") or "").strip()
                if not target_agent:
                    continue
                commands.append(
                    {
                        "target_agent": target_agent,
                        "task": str(item.get("task") or "").strip(),
                        "focus": str(item.get("focus") or "").strip(),
                        "expected_output": str(item.get("expected_output") or "").strip(),
                    }
                )
        if not str(normalized.get("chat_message") or "").strip():
            normalized["chat_message"] = "我来拆解问题并给各专家Agent下达命令。"
        normalized["commands"] = commands
        return normalized

    def _normalize_normal_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        chat_message = str(parsed.get("chat_message") or "").strip()
        analysis = str(parsed.get("analysis") or "").strip()
        conclusion = str(parsed.get("conclusion") or analysis or "").strip()
        evidence = parsed.get("evidence_chain")
        if not isinstance(evidence, list):
            evidence = []
        evidence = [str(item).strip() for item in evidence if str(item).strip()][:3]

        confidence = parsed.get("confidence")
        try:
            confidence_value = float(confidence)
        except Exception:
            confidence_value = 0.66 if analysis or conclusion else 0.45
        confidence_value = max(0.0, min(1.0, confidence_value))

        if not analysis and raw_content:
            analysis = raw_content[:220]
        if not conclusion:
            conclusion = analysis
        if not chat_message:
            if conclusion and analysis and conclusion != analysis:
                chat_message = f"我的判断是：{conclusion}。依据是：{analysis[:120]}"
            elif conclusion:
                chat_message = f"我的判断是：{conclusion}"
            elif raw_content:
                chat_message = raw_content[:180]

        return {
            "chat_message": chat_message[:260],
            "analysis": analysis,
            "conclusion": conclusion,
            "evidence_chain": evidence,
            "confidence": confidence_value,
            "raw_text": raw_content[:1200],
        }

    def _normalize_judge_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        chat_message = str(parsed.get("chat_message") or "").strip()
        final_judgment = parsed.get("final_judgment")
        if not isinstance(final_judgment, dict) and any(
            key in parsed for key in ("root_cause", "evidence_chain", "fix_recommendation")
        ):
            final_judgment = parsed
        if not isinstance(final_judgment, dict):
            final_judgment = {}

        root_cause = final_judgment.get("root_cause")
        if isinstance(root_cause, str):
            root_cause = {
                "summary": root_cause,
                "category": "unknown",
                "confidence": 0.6,
            }
        elif not isinstance(root_cause, dict):
            recovered_root = self._extract_object_by_named_key(str(raw_content or ""), "root_cause")
            if isinstance(recovered_root, dict) and recovered_root.get("summary"):
                root_cause = recovered_root
            else:
                root_cause = {
                    "summary": self.JUDGE_FALLBACK_SUMMARY,
                    "category": "unknown",
                    "confidence": 0.5,
                }
        if isinstance(root_cause, dict):
            summary = str(root_cause.get("summary") or "").strip()
            if not summary:
                root_cause["summary"] = self.JUDGE_FALLBACK_SUMMARY
            else:
                root_cause["summary"] = summary
            if not root_cause.get("category"):
                root_cause["category"] = "unknown"
            try:
                root_cause["confidence"] = max(
                    0.0,
                    min(1.0, float(root_cause.get("confidence") or 0.5)),
                )
            except (TypeError, ValueError):
                root_cause["confidence"] = 0.5
        else:
            root_cause = {
                "summary": self.JUDGE_FALLBACK_SUMMARY,
                "category": "unknown",
                "confidence": 0.5,
            }

        evidence_chain = final_judgment.get("evidence_chain")
        if not isinstance(evidence_chain, list):
            evidence_chain = []
        evidence_items: List[Dict[str, Any]] = []
        for item in evidence_chain[:6]:
            if isinstance(item, dict):
                evidence_items.append(
                    {
                        "type": str(item.get("type") or "analysis"),
                        "description": str(
                            item.get("description")
                            or item.get("evidence")
                            or item.get("summary")
                            or ""
                        ),
                        "source": str(item.get("source") or "langgraph"),
                        "location": item.get("location"),
                        "strength": str(item.get("strength") or "medium"),
                    }
                )
            else:
                evidence_items.append(
                    {
                        "type": "analysis",
                        "description": str(item),
                        "source": "langgraph",
                        "location": None,
                        "strength": "medium",
                    }
                )

        fix_recommendation = final_judgment.get("fix_recommendation")
        if not isinstance(fix_recommendation, dict):
            fix_recommendation = {
                "summary": "建议先进行止损并补充监控告警",
                "steps": [],
                "code_changes_required": True,
                "rollback_recommended": False,
                "testing_requirements": [],
            }

        impact_analysis = final_judgment.get("impact_analysis")
        if not isinstance(impact_analysis, dict):
            impact_analysis = {
                "affected_services": [],
                "business_impact": "待评估",
                "affected_users": "待评估",
            }

        risk_assessment = final_judgment.get("risk_assessment")
        if not isinstance(risk_assessment, dict):
            risk_assessment = {
                "risk_level": "medium",
                "risk_factors": [],
                "mitigation_suggestions": [],
            }

        decision_rationale = parsed.get("decision_rationale")
        if not isinstance(decision_rationale, dict):
            decision_rationale = {
                "key_factors": [],
                "reasoning": raw_content[:400],
            }

        action_items = parsed.get("action_items")
        if not isinstance(action_items, list):
            action_items = []

        responsible_team = parsed.get("responsible_team")
        if not isinstance(responsible_team, dict):
            responsible_team = {
                "team": "待确认",
                "owner": "待确认",
            }

        confidence = parsed.get("confidence")
        try:
            confidence_value = float(confidence)
        except Exception:
            confidence_value = float(root_cause.get("confidence") or 0.6)
        confidence_value = max(0.0, min(1.0, confidence_value))
        if not chat_message:
            root_summary = str(root_cause.get("summary") or "").strip()
            if root_summary:
                chat_message = f"综合各位观点，我倾向结论是：{root_summary}"
            elif raw_content:
                chat_message = raw_content[:220]

        return {
            "chat_message": chat_message[:300],
            "final_judgment": {
                "root_cause": root_cause,
                "evidence_chain": evidence_items,
                "fix_recommendation": fix_recommendation,
                "impact_analysis": impact_analysis,
                "risk_assessment": risk_assessment,
            },
            "decision_rationale": decision_rationale,
            "action_items": action_items,
            "responsible_team": responsible_team,
            "confidence": confidence_value,
            "raw_text": raw_content[:1400],
        }

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
