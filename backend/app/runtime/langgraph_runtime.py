"""
LangGraph Runtime orchestration for multi-agent, multi-round debate.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
import json
from time import monotonic
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

import structlog
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.runtime.langgraph.builder import GraphBuilder
from app.runtime.langgraph.checkpointer import create_checkpointer, close_checkpointer
from app.runtime.langgraph.prompts import (
    coordinator_command_schema as coordinator_command_schema_template,
    judge_output_schema as judge_output_schema_template,
)
from app.runtime.langgraph.parsers import (
    extract_readable_text,
    normalize_agent_output as normalize_agent_output_parser,
    normalize_commander_output as normalize_commander_output_parser,
    normalize_judge_output,
    normalize_normal_output,
)
from app.runtime.langgraph.context_builders import (
    collect_peer_items_from_cards as collect_peer_items_from_cards_ctx,
    collect_peer_items_from_dialogue as collect_peer_items_from_dialogue_ctx,
    coordination_peer_items as coordination_peer_items_ctx,
    history_items_for_agent_prompt as history_items_for_agent_prompt_ctx,
    peer_items_for_collaboration_prompt as peer_items_for_collaboration_prompt_ctx,
    supervisor_recent_messages as supervisor_recent_messages_ctx,
)
from app.runtime.langgraph.agent_runner import AgentRunner
from app.runtime.langgraph.event_dispatcher import EventDispatcher
from app.runtime.langgraph.message_ops import (
    dedupe_new_messages as dedupe_new_messages_ops,
    merge_round_and_message_cards as merge_round_and_message_cards_ops,
    message_signature as message_signature_ops,
    messages_to_cards as messages_to_cards_ops,
    prune_history_cards as prune_history_cards_ops,
)
from app.runtime.langgraph.prompt_builder import PromptBuilder
from app.runtime.langgraph.phase_executor import PhaseExecutor
from app.runtime.langgraph.routing_strategy import HybridRouter
from app.runtime.langgraph.services.state_transition_service import StateTransitionService
from app.runtime.langgraph.services.routing_service import RoutingService
from app.runtime.langgraph.phase_manager import PhaseManager
from app.runtime.langgraph.session_compaction import SessionCompaction
from app.runtime.langgraph.doom_loop_guard import DoomLoopGuard
from app.runtime.langgraph.output_truncation import truncate_text as truncate_text_with_ref
from app.runtime.langgraph.work_log_manager import work_log_manager
from app.runtime.langgraph.mailbox import (
    clone_mailbox,
    compact_mailbox,
    dequeue_messages,
    enqueue_message,
)
from app.runtime.langgraph.routing import (
    fallback_supervisor_route as fallback_supervisor_route_helper,
    judge_is_ready as judge_is_ready_route,
    recent_agent_card as recent_agent_card_route,
    route_from_commander_output as route_from_commander_output_helper,
    round_agent_counts as round_agent_counts_route,
    route_guardrail as route_guardrail_helper,
)
from app.runtime.langgraph.nodes import (
    execute_supervisor_decide,
    execute_single_phase_agent,
)
from app.runtime.langgraph.specs import (
    agent_sequence as build_agent_sequence,
    problem_analysis_agent_spec as build_problem_analysis_agent_spec,
)
from app.runtime.langgraph.state import (
    AgentSpec,
    DebateExecState as _DebateExecState,
    DebateTurn,
    build_session_init_update,
    structured_state_snapshot,
)
from app.runtime.messages import AgentEvidence, AgentMessage, FinalVerdict, RoundCheckpoint
from app.runtime.session_store import runtime_session_store
from app.runtime.trace_lineage import lineage_recorder
from app.services.agent_tool_context_service import agent_tool_context_service

logger = structlog.get_logger()


class LangGraphRuntimeOrchestrator:
    """
    基于 LangGraph 的运行时编排器。

    这是多 Agent 分析主流程的总控类，主要负责：
    1. 会话初始化与超时边界
    2. 运行策略 / deployment profile 生效
    3. Graph 构建与执行
    4. 事件、轨迹、checkpoint 和最终结论收口

    它本身尽量不承载过多细节执行逻辑，重执行部分会下沉到：
    - PhaseExecutor
    - AgentRunner
    - PromptBuilder
    - RoutingService / StateTransitionService
    """

    MAX_HISTORY_ITEMS = 4
    PARALLEL_ANALYSIS_AGENTS = (
        "LogAgent",
        "DomainAgent",
        "CodeAgent",
        "DatabaseAgent",
        "MetricsAgent",
        "ChangeAgent",
        "RunbookAgent",
        "RuleSuggestionAgent",
    )
    KEY_EVIDENCE_AGENTS = (
        "LogAgent",
        "CodeAgent",
        "DatabaseAgent",
        "MetricsAgent",
    )
    ANALYSIS_PRIORITY_BATCHES = (
        ("DatabaseAgent", "MetricsAgent"),
        ("LogAgent", "CodeAgent"),
    )
    COLLABORATION_PEER_LIMIT = 2
    STREAM_CHUNK_SIZE = 160
    STREAM_MAX_CHUNKS = 16
    JUDGE_FALLBACK_SUMMARY = "需要进一步分析"
    MAX_DISCUSSION_STEPS_PER_ROUND = 12
    DIALOGUE_PROMPT_CHAR_BUDGET = 900

    def __init__(self, consensus_threshold: float = 0.85, max_rounds: int = 1):
        """
        初始化运行时编排器的核心依赖。

        注意这里不是在“启动一次分析”，而是在装配执行器本身：
        - 挂好事件分发器
        - 初始化路由/阶段/状态服务
        - 建立 LLM 并发控制和 checkpoint 依赖
        """
        self.consensus_threshold = consensus_threshold
        self.max_rounds = max_rounds
        self.min_rounds = 1
        self.session_id: Optional[str] = None
        self.trace_id: str = ""
        self.turns: List[DebateTurn] = []
        self._active_round_commands: Dict[str, Dict[str, Any]] = {}
        self._event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
        self._input_context: Dict[str, Any] = {}
        self._enable_collaboration: bool = bool(settings.DEBATE_ENABLE_COLLABORATION)
        self._enable_critique: bool = bool(settings.DEBATE_ENABLE_CRITIQUE)
        self._require_verification_plan: bool = True
        self._deployment_profile_name: str = ""
        self._execution_mode_name: str = "standard"
        self._event_dispatcher = EventDispatcher()
        self._agent_runner = AgentRunner(self)
        self._routing_strategy = HybridRouter()
        self._routing_service = RoutingService()
        self._work_log_manager = work_log_manager
        self._llm_semaphore_limit = max(1, int(settings.LLM_MAX_CONCURRENCY or 1))
        self._llm_semaphore: Optional[asyncio.Semaphore] = None
        self._llm_semaphore_loop: Optional[asyncio.AbstractEventLoop] = None
        self._session_timeout_seconds: Optional[float] = None
        self._session_deadline_monotonic: Optional[float] = None
        self._graph_checkpointer = create_checkpointer(settings)
        self._prompt_builder = PromptBuilder(
            max_rounds=self.max_rounds,
            max_history_items=self.MAX_HISTORY_ITEMS,
            to_json=self._to_compact_json,
            derive_conversation_state_with_context=self._derive_conversation_state_with_context,
        )
        self._phase_executor = PhaseExecutor(self)
        self._phase_manager = PhaseManager()
        self._session_compaction = SessionCompaction()
        self._doom_loop_guard = DoomLoopGuard(threshold=3)
        self._state_transition_service = StateTransitionService(
            dedupe_new_messages=self._dedupe_new_messages,
            message_deltas_from_cards=self._message_deltas_from_cards,
            derive_conversation_state=self._derive_conversation_state_with_context,
            messages_to_cards=lambda msgs: self._messages_to_cards(msgs, limit=20),
            merge_round_and_message_cards=lambda round_cards, message_cards: merge_round_and_message_cards_ops(
                round_cards,
                message_cards,
                limit=20,
            ),
            structured_snapshot=structured_state_snapshot,
        )

        logger.info(
            "langgraph_runtime_orchestrator_initialized",
            model=settings.llm_model,
            base_url=settings.LLM_BASE_URL,
            max_rounds=max_rounds,
            consensus_threshold=consensus_threshold,
            prompt_template_version=self._prompt_builder.template_version,
        )

    def _configure_runtime_policy(self, context: Dict[str, Any]) -> None:
        """
        根据 execution mode、runtime strategy 和 deployment profile 计算当前会话的运行策略。

        这里真正决定的是本轮会话的“行为边界”，例如：
        - 哪些 analysis agent 会参与
        - 每轮最多允许多少讨论步
        - 是否开启 collaboration / critique / verification
        """
        execution_mode = str((context or {}).get("execution_mode") or "standard").strip().lower()
        deployment_profile = (context or {}).get("deployment_profile")
        runtime_strategy = (context or {}).get("runtime_strategy")
        phase_mode = ""
        if isinstance(runtime_strategy, dict):
            phase_mode = str(runtime_strategy.get("phase_mode") or "").strip().lower()

        core_agents = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")
        balanced_agents = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent", "MetricsAgent")
        fast_agents = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent", "MetricsAgent", "ChangeAgent")

        if phase_mode in {"economy", "failfast"} or execution_mode == "quick":
            selected_agents = core_agents
            max_discussion_steps = 4
            enable_critique = False
            enable_collaboration = False
            require_verification_plan = False
        elif phase_mode == "fast_track" or execution_mode in {"background", "async"}:
            selected_agents = fast_agents
            max_discussion_steps = 10
            enable_critique = False
            enable_collaboration = False
            require_verification_plan = False
        else:
            selected_agents = balanced_agents
            max_discussion_steps = 8
            enable_critique = bool(settings.DEBATE_ENABLE_CRITIQUE)
            enable_collaboration = bool(settings.DEBATE_ENABLE_COLLABORATION)
            require_verification_plan = True

        if isinstance(deployment_profile, dict) and deployment_profile.get("name"):
            self._deployment_profile_name = str(deployment_profile.get("name") or "").strip().lower()
            selected_agents = tuple(
                str(name or "").strip()
                for name in list(deployment_profile.get("analysis_agents") or [])
                if str(name or "").strip()
            ) or selected_agents
            enable_collaboration = bool(deployment_profile.get("collaboration_enabled") or False)
            enable_critique = bool(deployment_profile.get("critique_enabled") or False)
            require_verification_plan = bool(deployment_profile.get("require_verification_plan") or False)
        else:
            self._deployment_profile_name = ""
        self._execution_mode_name = execution_mode

        self.PARALLEL_ANALYSIS_AGENTS = tuple(selected_agents)
        self.MAX_DISCUSSION_STEPS_PER_ROUND = int(max_discussion_steps)
        self._enable_collaboration = bool(enable_collaboration)
        self._enable_critique = bool(enable_critique)
        self._require_verification_plan = bool(require_verification_plan)
        logger.info(
            "runtime_policy_applied",
            execution_mode=execution_mode,
            phase_mode=phase_mode or "standard",
            deployment_profile=(
                str(deployment_profile.get("name") or "")
                if isinstance(deployment_profile, dict)
                else ""
            ),
            parallel_analysis_agents=list(self.PARALLEL_ANALYSIS_AGENTS),
            max_discussion_steps=self.MAX_DISCUSSION_STEPS_PER_ROUND,
            enable_collaboration=self._enable_collaboration,
            enable_critique=self._enable_critique,
            require_verification_plan=self._require_verification_plan,
        )

    def _get_llm_semaphore(self) -> asyncio.Semaphore:
        """获取当前事件循环绑定的 LLM 并发 semaphore，避免跨 loop 复用失效。"""
        loop = asyncio.get_running_loop()
        if self._llm_semaphore is None or self._llm_semaphore_loop is not loop:
            self._llm_semaphore = asyncio.Semaphore(self._llm_semaphore_limit)
            self._llm_semaphore_loop = loop
        return self._llm_semaphore

    def _analysis_batch_limit(self, *, collaboration: bool = False) -> int:
        """
        计算 analysis / collaboration 阶段单批可并发 Agent 数。

        这里故意保留至少一个槽位给收口链路，避免分析波次把
        `ProblemAnalysisAgent` / `JudgeAgent` 直接挤出队列。
        """
        reserve_slots = 1 if self._llm_semaphore_limit > 1 else 0
        batch_limit = max(1, self._llm_semaphore_limit - reserve_slots)

        # investigation_full / production_governed 会带更多专家、更长 prompt 和更重的收口链路。
        # 这里主动把分析波次压窄，优先保证 commander / judge 不被并行波次挤出队列。
        if self._deployment_profile_name in {"investigation_full", "production_governed"}:
            reserve_slots = 2 if self._llm_semaphore_limit > 2 else reserve_slots
            batch_limit = max(1, self._llm_semaphore_limit - reserve_slots)
            if collaboration:
                return 1
            return max(1, min(batch_limit, 2))

        if collaboration:
            return max(1, min(batch_limit, 2))
        return batch_limit

    @staticmethod
    def _is_rate_limited_error(error_text: str) -> bool:
        """统一判断错误文本是否属于模型限流/过载类问题。"""
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
        """
        执行一次完整的 LangGraph 会话。

        高层流程如下：
        1. 绑定 trace/session 和事件回调
        2. 根据上下文应用运行策略
        3. 构建 Graph 并调用 `ainvoke`
        4. 收集最终 payload、写入轨迹摘要
        5. 统一做异常和资源清理
        """
        self.turns = []
        self._active_round_commands = {}
        self._event_callback = event_callback
        self._input_context = dict(context or {})
        self.session_id = f"ags_{uuid4().hex[:20]}"
        self.trace_id = str(context.get("trace_id") or "")
        self._event_dispatcher.bind(
            trace_id=self.trace_id,
            session_id=str(self.session_id or ""),
            callback=event_callback,
        )
        self._configure_runtime_policy(context)
        configured_session_timeout = float(context.get("session_timeout_seconds") or 0.0)
        if configured_session_timeout <= 0:
            configured_session_timeout = float(max(30, int(settings.DEBATE_TIMEOUT or 600)))
        self._session_timeout_seconds = configured_session_timeout
        self._session_deadline_monotonic = monotonic() + configured_session_timeout
        await lineage_recorder.append(
            session_id=str(self.session_id),
            trace_id=self.trace_id,
            kind="session",
            phase="coordination",
            event_type="session_started",
            payload={
                "context_keys": list((context or {}).keys()),
                "session_timeout_seconds": configured_session_timeout,
            },
        )
        context_summary = {
            "incident_summary": {
                "title": str(context.get("title") or "")[:160],
                "description": str(context.get("description") or "")[:280],
                "severity": str(context.get("severity") or ""),
                "service_name": str(context.get("service_name") or ""),
            },
            "log_excerpt": str(context.get("log_content") or "")[:1400],
            "parsed_data": context.get("parsed_data") or {},
            "interface_mapping": context.get("interface_mapping") or {},
            "investigation_leads": context.get("investigation_leads") or {},
            "runtime_assets_count": len(context.get("runtime_assets") or []),
            "dev_assets_count": len(context.get("dev_assets") or []),
            "design_assets_count": len(context.get("design_assets") or []),
            "execution_mode": str(context.get("execution_mode") or "standard"),
            "available_analysis_agents": list(self.PARALLEL_ANALYSIS_AGENTS),
        }

        # Graph 每次执行时按当前策略即时构建，避免把旧会话策略残留到新会话。
        graph_builder = GraphBuilder(self)
        graph = graph_builder.build(self._agent_sequence())
        app = graph.compile(checkpointer=self._graph_checkpointer)

        try:
            result_state = await app.ainvoke(
                {
                    "context": context,
                    "context_summary": context_summary,
                },
                config={"configurable": {"thread_id": str(self.session_id)}},
            )
            final_payload = dict(result_state.get("final_payload") or {})
            await lineage_recorder.append(
                session_id=str(self.session_id),
                trace_id=self.trace_id,
                kind="summary",
                phase="judgment",
                event_type="session_completed",
                confidence=float(final_payload.get("confidence") or 0.0),
                payload={
                    "consensus_reached": bool(final_payload.get("consensus_reached") or False),
                    "executed_rounds": int(final_payload.get("executed_rounds") or 0),
                },
            )
            return final_payload
        except Exception:
            if self.session_id:
                await runtime_session_store.fail(self.session_id)
                await lineage_recorder.append(
                    session_id=str(self.session_id),
                    trace_id=self.trace_id,
                    kind="summary",
                    phase="failed",
                    event_type="session_failed",
                )
            raise
        finally:
            self._session_timeout_seconds = None
            self._session_deadline_monotonic = None

    async def _graph_init_session(self, state: _DebateExecState) -> _DebateExecState:
        """初始化运行时会话，并把首个 session_created 事件落到审计流。"""
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
        return build_session_init_update(self.MAX_DISCUSSION_STEPS_PER_ROUND)

    def _route_after_analysis_parallel(self, state: _DebateExecState) -> str:
        """决定并行分析阶段结束后下一步该走哪个节点。"""
        return self._routing_service.route_after_analysis_parallel(
            enable_collaboration=self._enable_collaboration
        )

    def _route_after_critic(self, state: _DebateExecState) -> str:
        """决定质疑阶段结束后下一步该走哪个节点。"""
        return self._routing_service.route_after_critic(
            enable_critique=self._enable_critique
        )

    def _supervisor_step_to_node(self, next_step: str) -> str:
        """把 supervisor 产出的 step 名称映射成 LangGraph 节点名。"""
        return self._routing_service.supervisor_step_to_node(next_step)

    def _route_after_supervisor_decide(self, state: _DebateExecState) -> str:
        """根据 supervisor 的决策结果选择下一跳节点。"""
        return self._routing_service.route_after_supervisor_decide(state)

    def _route_after_round_evaluate(self, state: _DebateExecState) -> str:
        """根据 round_evaluate 的结果选择下一轮或终态节点。"""
        return self._routing_service.route_after_round_evaluate(state)

    def _round_discussion_budget(self) -> int:
        """计算当前配置下每轮允许消耗的讨论步数预算。"""
        return self._routing_service.round_discussion_budget(
            base_steps=self.MAX_DISCUSSION_STEPS_PER_ROUND,
            enable_collaboration=self._enable_collaboration,
            enable_critique=self._enable_critique,
        )

    def _step_for_agent(self, agent_name: str) -> str:
        """根据 Agent 名称反查它在图中的逻辑 step。"""
        return self._routing_service.step_for_agent(agent_name)

    def _agent_from_step(self, step: str) -> str:
        """根据图 step 反查对应的 Agent 名称。"""
        return self._routing_service.agent_from_step(step)

    def _round_turns_from_state(self, state: _DebateExecState) -> List[DebateTurn]:
        """从全量 turn 历史中切出当前 round 的 turn 视图。"""
        start_index = max(0, int(state.get("round_start_turn_index") or 0))
        return list(self.turns[start_index:])

    def _round_cards_from_state(self, state: _DebateExecState) -> List[AgentEvidence]:
        """从 state 中切出当前 round 的证据卡片集合。"""
        history_cards = list(state.get("history_cards") or [])
        start_index = max(0, int(state.get("round_start_turn_index") or 0))
        if start_index <= 0:
            return history_cards
        # round_start_turn_index is indexed against self.turns; cards track the same append order.
        return history_cards[start_index:]

    def _messages_to_cards(
        self,
        messages: List[Any],
        *,
        limit: int = 12,
    ) -> List[AgentEvidence]:
        """把 LangGraph messages 投影成统一的证据卡片结构。"""
        return messages_to_cards_ops(messages, limit=limit)

    def _history_cards_for_state(
        self,
        state: Dict[str, Any],
        *,
        limit: int = 20,
    ) -> List[AgentEvidence]:
        """Build execution cards with message-first projection.

        `history_cards` remains as a UI/display projection; runtime decisions should
        primarily consume cards derived from LangGraph `messages`.
        """
        stored_cards = list(state.get("history_cards") or [])
        message_cards = self._messages_to_cards(list(state.get("messages") or []), limit=max(8, limit))
        return merge_round_and_message_cards_ops(stored_cards, message_cards, limit=max(8, limit))

    def _round_cards_for_routing(self, state: _DebateExecState) -> List[AgentEvidence]:
        """为路由判断准备 round cards，并补上最新消息投影。"""
        round_cards = self._round_cards_from_state(state)
        message_cards = self._messages_to_cards(list(state.get("messages") or []), limit=12)
        return merge_round_and_message_cards_ops(round_cards, message_cards, limit=20)

    def _recent_judge_turn(self, round_turns: List[DebateTurn]) -> Optional[DebateTurn]:
        """返回当前轮里最近一次 JudgeAgent 的 turn。"""
        for turn in reversed(round_turns):
            if turn.agent_name == "JudgeAgent":
                return turn
        return None

    def _recent_judge_card(self, round_cards: List[AgentEvidence]) -> Optional[AgentEvidence]:
        """返回当前轮里最近一次 JudgeAgent 的证据卡片。"""
        for card in reversed(round_cards):
            if card.agent_name == "JudgeAgent":
                return card
        return None

    def _recent_agent_card(
        self,
        round_cards: List[AgentEvidence],
        agent_name: str,
    ) -> Optional[AgentEvidence]:
        """返回指定 Agent 最近一张可用于路由判断的卡片。"""
        return recent_agent_card_route(round_cards, agent_name)

    def _round_agent_counts(self, round_cards: List[AgentEvidence]) -> Dict[str, int]:
        """统计当前轮各 Agent 已产出的卡片数量。"""
        return round_agent_counts_route(round_cards)

    def _judge_is_ready(self, round_cards: List[AgentEvidence]) -> bool:
        """判断当前证据覆盖是否足以进入 Judge 阶段。"""
        return judge_is_ready_route(
            round_cards,
            state={"agent_outputs": {card.agent_name: card.raw_output for card in round_cards if isinstance(card.raw_output, dict)}},
            parallel_analysis_agents=self.PARALLEL_ANALYSIS_AGENTS,
            debate_enable_critique=self._enable_critique,
        )

    def _route_guardrail(
        self,
        *,
        state: _DebateExecState,
        round_cards: List[AgentEvidence],
        route_decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        """对路由结果施加门禁，防止空转、误收口或越界跳转。"""
        return route_guardrail_helper(
            state=state,
            round_cards=round_cards,
            route_decision=route_decision,
            consensus_threshold=self.consensus_threshold,
            max_discussion_steps_default=self.MAX_DISCUSSION_STEPS_PER_ROUND,
            parallel_analysis_agents=self.PARALLEL_ANALYSIS_AGENTS,
            debate_enable_critique=self._enable_critique,
        )

    def _fallback_supervisor_route(
        self,
        state: _DebateExecState,
        round_cards: List[AgentEvidence],
    ) -> Dict[str, Any]:
        """在 supervisor 输出不可用时生成谨慎的兜底路由决策。"""
        return fallback_supervisor_route_helper(
            state=state,
            round_cards=round_cards,
            debate_enable_critique=self._enable_critique,
            require_verification=self._require_verification_plan,
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
        """把主 Agent 的结构化输出转换成实际可执行的路由决策。"""
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
        """把证据卡片压缩成可回灌给模型的 AIMessage。"""
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
        """从消息流中抽取可放入 Prompt 的对话摘要条目。"""
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

    def _message_signature(self, msg: Any) -> str:
        """为消息生成稳定签名，供去重逻辑复用。"""
        return message_signature_ops(msg)

    def _dedupe_new_messages(
        self,
        existing_messages: List[Any],
        new_messages: List[Any],
    ) -> List[Any]:
        """在写回 state 前去掉本轮新增消息里的重复项。"""
        return dedupe_new_messages_ops(existing_messages, new_messages)

    def _message_deltas_from_cards(self, cards: List[AgentEvidence]) -> List[AIMessage]:
        """把新增 cards 转成需要追加到 message history 的增量消息。"""
        deltas: List[AIMessage] = []
        for card in cards:
            msg = self._card_to_ai_message(card)
            if msg is not None:
                deltas.append(msg)
        return deltas

    def _derive_conversation_state(self, history_cards: List[AgentEvidence]) -> Dict[str, Any]:
        """从历史卡片恢复主 Agent 需要的会话摘要状态。"""
        return self._derive_conversation_state_with_context(history_cards)

    def _derive_conversation_state_with_context(
        self,
        history_cards: List[AgentEvidence],
        *,
        messages: Optional[List[Any]] = None,
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """结合历史卡片、消息流和既有输出派生完整会话状态。"""
        claims: List[Dict[str, Any]] = []
        open_questions: List[str] = []
        agent_outputs: Dict[str, Dict[str, Any]] = {
            str(name or "").strip(): (payload if isinstance(payload, dict) else {})
            for name, payload in dict(existing_agent_outputs or {}).items()
            if str(name or "").strip()
        }
        cards = list(history_cards or [])
        if messages:
            cards.extend(self._messages_to_cards(messages, limit=12))
        merged_cards: List[AgentEvidence] = []
        seen_card_sig: set[tuple[str, str]] = set()
        for card in cards:
            sig = (
                str(card.agent_name or "").strip(),
                str(card.conclusion or "").strip()[:120] or str(card.summary or "").strip()[:120],
            )
            if sig in seen_card_sig:
                continue
            seen_card_sig.add(sig)
            merged_cards.append(card)

        for card in merged_cards:
            output = card.raw_output if isinstance(getattr(card, "raw_output", None), dict) else {}
            name = str(card.agent_name or "").strip()
            if not name:
                continue
            if output:
                previous = agent_outputs.get(name) or {}
                agent_outputs[name] = {**previous, **output}
            else:
                agent_outputs.setdefault(name, {})
            conclusion = str(card.conclusion or output.get("conclusion") or "").strip()
            if conclusion:
                claims.append(
                    {
                        "agent_name": name,
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
        """执行 Supervisor 路由决策节点，决定下一步进入哪个图节点。"""
        return await execute_supervisor_decide(self, state)

    def _graph_apply_step_result(
        self,
        state: _DebateExecState,
        result: Optional[Dict[str, Any]],
    ) -> _DebateExecState:
        """把单个节点返回的增量结果合并回全局状态。"""
        return self._state_transition_service.apply_step_result(state, result)

    async def _graph_round_start(self, state: _DebateExecState) -> _DebateExecState:
        """
        启动新一轮分析。

        这一阶段会先整理历史卡片、对话摘要和压缩上下文，再调用
        `ProblemAnalysisAgent` 生成本轮命令，并把命令写入 mailbox，
        供后续并行分析阶段逐个专家 Agent 消费。
        """
        current_round = int(state.get("current_round") or 0) + 1
        if current_round > max(1, self.max_rounds):
            return {"continue_next_round": False}
        history_cards = self._history_cards_for_state(state, limit=20)
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=4,
            char_budget=520,
        )
        context_summary = state.get("context_summary") or {}
        compact_context = self._session_compaction.compact_context(
            self._compact_round_context(context_summary),
            max_len=3200,
        )
        phase_meta = self._phase_manager.summarize(
            current_round=current_round,
            max_rounds=max(1, self.max_rounds),
        )
        await self._emit_event(
            {
                "type": "round_started",
                "loop_round": current_round,
                "max_rounds": self.max_rounds,
                "phase": phase_meta.get("phase"),
                "mode": "langgraph_runtime",
            }
        )
        # 主 Agent 在这一轮只做“下发命令”，不直接产出最终根因。
        commander_result = await self._run_problem_analysis_commander(
            loop_round=current_round,
            compact_context=compact_context,
            history_cards=history_cards,
            dialogue_items=dialogue_items,
            existing_agent_outputs=dict(state.get("agent_outputs") or {}),
        )
        commands = dict(commander_result.get("commands") or {})
        self._active_round_commands = commands
        mailbox = clone_mailbox(state.get("agent_mailbox") or {})
        for target, command in commands.items():
            command_text = str((command or {}).get("task") or "").strip()
            focus = str((command or {}).get("focus") or "").strip()
            expected = str((command or {}).get("expected_output") or "").strip()
            enqueue_message(
                mailbox,
                receiver=target,
                message=AgentMessage(
                    sender="ProblemAnalysisAgent",
                    receiver=target,
                    message_type="command",
                    content={
                        "task": command_text,
                        "focus": focus,
                        "expected_output": expected,
                    },
                ),
            )
        preseed_route = self._route_from_commander_output(
            payload=commander_result,
            state=state,
            round_cards=self._round_cards_for_routing(
                {
                    "history_cards": history_cards,
                    "messages": list(state.get("messages") or []),
                    "round_start_turn_index": len(self.turns) - 1,
                }
            ),
        )
        next_state = {
            "current_round": current_round,
            "continue_next_round": False,
            "history_cards": history_cards,
            "agent_commands": commands,
            "agent_mailbox": compact_mailbox(mailbox),
            "next_step": str(preseed_route.get("next_step") or ""),
            "round_start_turn_index": len(self.turns),
            "discussion_step_count": 0,
            "max_discussion_steps": self._round_discussion_budget(),
            "supervisor_stop_requested": bool(preseed_route.get("should_stop") or False),
            "supervisor_stop_reason": str(preseed_route.get("stop_reason") or ""),
            **self._derive_conversation_state_with_context(
                history_cards,
                messages=list(state.get("messages") or []),
                existing_agent_outputs=dict(state.get("agent_outputs") or {}),
            ),
        }
        merged_preview = {**dict(state), **next_state}
        return {**next_state, **structured_state_snapshot(merged_preview)}

    async def _graph_analysis_parallel(self, state: _DebateExecState) -> _DebateExecState:
        """
        执行并行分析阶段。

        这里会按当前运行策略把专家 Agent 拆成批次执行，避免一次性占满
        LLM 队列，同时确保关键证据 Agent 优先得到执行机会。
        """
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = self._history_cards_for_state(state, limit=20)
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=4,
            char_budget=520,
        )
        compact_context = self._compact_round_context(context_summary)
        agent_mailbox = clone_mailbox(state.get("agent_mailbox") or {})
        await self._run_parallel_analysis_phase(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
            agent_mailbox=agent_mailbox,
        )
        return {"history_cards": history_cards, "agent_mailbox": compact_mailbox(agent_mailbox)}

    async def _graph_analysis_collaboration(self, state: _DebateExecState) -> _DebateExecState:
        """执行专家间协作阶段，让分析 Agent 互相补充证据或纠正结论。"""
        if not self._enable_collaboration:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = self._history_cards_for_state(state, limit=20)
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=5,
            char_budget=620,
        )
        compact_context = self._compact_round_context(context_summary)
        agent_mailbox = clone_mailbox(state.get("agent_mailbox") or {})
        await self._run_collaboration_phase(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            dialogue_items=dialogue_items,
            agent_mailbox=agent_mailbox,
        )
        return {"history_cards": history_cards, "agent_mailbox": compact_mailbox(agent_mailbox)}

    async def _graph_critic(self, state: _DebateExecState) -> _DebateExecState:
        """执行质疑阶段，让 `CriticAgent` 针对当前主结论提出反证。"""
        if not self._enable_critique:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = self._history_cards_for_state(state, limit=20)
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=5,
            char_budget=620,
        )
        compact_context = self._compact_round_context(context_summary)
        agent_mailbox = clone_mailbox(state.get("agent_mailbox") or {})
        inbox_messages, agent_mailbox = dequeue_messages(agent_mailbox, receiver="CriticAgent")
        execution_result = await execute_single_phase_agent(
            self,
            agent_name="CriticAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
            agent_mailbox=agent_mailbox,
        )
        agent_mailbox = clone_mailbox(execution_result.get("agent_mailbox") or agent_mailbox)
        return {"history_cards": history_cards, "agent_mailbox": compact_mailbox(agent_mailbox)}

    async def _graph_rebuttal(self, state: _DebateExecState) -> _DebateExecState:
        """执行反驳阶段，让 `RebuttalAgent` 回应质疑并补充证据。"""
        if not self._enable_critique:
            return {}
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = self._history_cards_for_state(state, limit=20)
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=5,
            char_budget=620,
        )
        compact_context = self._compact_round_context(context_summary)
        agent_mailbox = clone_mailbox(state.get("agent_mailbox") or {})
        inbox_messages, agent_mailbox = dequeue_messages(agent_mailbox, receiver="RebuttalAgent")
        execution_result = await execute_single_phase_agent(
            self,
            agent_name="RebuttalAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
            agent_mailbox=agent_mailbox,
        )
        agent_mailbox = clone_mailbox(execution_result.get("agent_mailbox") or agent_mailbox)
        return {"history_cards": history_cards, "agent_mailbox": compact_mailbox(agent_mailbox)}

    async def _graph_judge(self, state: _DebateExecState) -> _DebateExecState:
        """
        执行裁决阶段。

        `JudgeAgent` 会综合本轮专家输出、协作结果和质疑/反驳信息，
        形成最终结构化裁决，同时由主 Agent 补发最终摘要事件。
        """
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = self._history_cards_for_state(state, limit=20)
        dialogue_items = self._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=6,
            char_budget=760,
        )
        compact_context = self._compact_round_context(context_summary)
        agent_mailbox = clone_mailbox(state.get("agent_mailbox") or {})
        inbox_messages, agent_mailbox = dequeue_messages(agent_mailbox, receiver="JudgeAgent")
        execution_result = await execute_single_phase_agent(
            self,
            agent_name="JudgeAgent",
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
            agent_mailbox=agent_mailbox,
        )
        agent_mailbox = clone_mailbox(execution_result.get("agent_mailbox") or agent_mailbox)
        await self._emit_problem_analysis_final_summary(
            loop_round=loop_round,
            history_cards=history_cards,
        )
        return {"history_cards": history_cards, "agent_mailbox": compact_mailbox(agent_mailbox)}

    async def _graph_round_evaluate(self, state: _DebateExecState) -> _DebateExecState:
        """
        评估当前轮次是否已经可以收口。

        这里会同时考虑：
        - Judge 是否已返回有效结论
        - 置信度是否达到共识阈值
        - Supervisor 是否主动请求停止
        - 轮次预算是否还有余量
        """
        current_round = int(state.get("current_round") or 1)
        history_cards = self._history_cards_for_state(state, limit=20)
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
        """按名称查找 AgentSpec。"""
        for spec in self._agent_sequence():
            if spec.name == agent_name:
                return spec
        return None

    def _problem_analysis_agent_spec(self) -> AgentSpec:
        """返回 ProblemAnalysisAgent 的标准规格定义。"""
        return build_problem_analysis_agent_spec()

    def _coordinator_command_schema(self) -> Dict[str, Any]:
        """返回 commander/supervisor 使用的结构化命令 Schema。"""
        return coordinator_command_schema_template()

    def _prompt_template_version(self) -> str:
        """返回当前 Prompt 模板版本号，便于审计和回放。"""
        return str(self._prompt_builder.template_version or "unknown")

    def _build_problem_analysis_commander_prompt(
        self,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """组装 ProblemAnalysisAgent 的 commander Prompt。"""
        prompt = self._prompt_builder.build_commander_prompt(
            loop_round=loop_round,
            context=context,
            history_cards=history_cards,
            work_log_context=self._work_log_context(limit=18),
            dialogue_items=dialogue_items,
            existing_agent_outputs=existing_agent_outputs,
        )
        if loop_round == 1 and self._execution_mode_name in {"quick", "background", "async"}:
            max_chars = 1700 if self._execution_mode_name == "quick" else 2200
            return self._compact_prompt_for_retry(prompt, max_chars=max_chars)
        return prompt

    def _build_problem_analysis_supervisor_prompt(
        self,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_history_cards: List[AgentEvidence],
        discussion_step_count: int,
        max_discussion_steps: int,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """组装 supervisor 决策使用的 Prompt。"""
        return self._prompt_builder.build_supervisor_prompt(
            loop_round=loop_round,
            context=context,
            history_cards=history_cards,
            round_history_cards=round_history_cards,
            discussion_step_count=discussion_step_count,
            max_discussion_steps=max_discussion_steps,
            work_log_context=self._work_log_context(limit=18),
            dialogue_items=dialogue_items,
            existing_agent_outputs=existing_agent_outputs,
        )

    def _coordination_peer_items(
        self,
        history_cards: List[AgentEvidence],
        dialogue_items: List[Dict[str, Any]],
        existing_agent_outputs: Dict[str, Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        # compatibility shim: moved to context_builders.coordination_peer_items
        """整理 commander 协调阶段要看的同伴结论摘要。"""
        return coordination_peer_items_ctx(
            history_cards=history_cards,
            dialogue_items=dialogue_items,
            existing_agent_outputs=existing_agent_outputs,
            limit=limit,
        )

    def _supervisor_recent_messages(
        self,
        round_history_cards: List[AgentEvidence],
        dialogue_items: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        # compatibility shim: moved to context_builders.supervisor_recent_messages
        """整理 supervisor 最近需要关注的消息摘要。"""
        return supervisor_recent_messages_ctx(
            round_history_cards=round_history_cards,
            dialogue_items=dialogue_items,
            limit=limit,
        )

    def _extract_agent_commands_from_payload(
        self,
        payload: Dict[str, Any],
        *,
        fill_defaults: bool,
        targets_hint: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """从 commander/supervisor 载荷里提取标准化的 Agent 命令集合。"""
        def _normalize_items(value: Any, *, limit: int = 20, width: int = 120) -> List[str]:
            """把列表字段清洗成稳定的短文本数组。"""
            if not isinstance(value, list):
                return []
            picks: List[str] = []
            for item in value:
                text = str(item or "").strip()
                if not text:
                    continue
                picks.append(text[:width])
            # preserve order while deduplicating
            return list(dict.fromkeys(picks))[:limit]

        def _normalize_skill_hints(value: Any) -> List[str]:
            """把 skill hints 清洗成稳定的提示语列表。"""
            return _normalize_items(value, limit=8, width=80)

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
                    "use_tool": item.get("use_tool"),
                    "database_tables": _normalize_items(item.get("database_tables")),
                    "api_endpoints": _normalize_items(item.get("api_endpoints"), limit=12, width=180),
                    "service_names": _normalize_items(item.get("service_names"), limit=12, width=120),
                    "code_artifacts": _normalize_items(item.get("code_artifacts"), limit=16, width=180),
                    "class_names": _normalize_items(item.get("class_names"), limit=16, width=120),
                    "monitor_items": _normalize_items(item.get("monitor_items"), limit=16, width=160),
                    "dependency_services": _normalize_items(item.get("dependency_services"), limit=16, width=120),
                    "trace_ids": _normalize_items(item.get("trace_ids"), limit=8, width=120),
                    "error_keywords": _normalize_items(item.get("error_keywords"), limit=12, width=120),
                    "skill_hints": _normalize_skill_hints(item.get("skill_hints")),
                }

        defaults = {
            "LogAgent": "分析错误日志、502 与 CPU 异常的直接证据链",
            "DomainAgent": "根据接口 URL 映射领域/聚合根/责任田并确认负责团队",
            "CodeAgent": "定位可能代码瓶颈、连接池/线程池/慢SQL风险点",
            "DatabaseAgent": "读取数据库表结构/索引/慢SQL/TopSQL/session状态并给出瓶颈判断",
            "MetricsAgent": "提取 CPU/线程/连接池/错误率指标异常窗口，给出关键时间点与阈值",
            "ChangeAgent": "分析故障时间窗前后的发布/提交变更，给出可疑变更候选",
            "RunbookAgent": "检索相似故障案例与SOP，给出可执行处置步骤和差异点",
            "CriticAgent": "质疑前述结论中的证据缺口和假设跳跃",
            "RebuttalAgent": "针对质疑补充证据并收敛执行建议",
            "JudgeAgent": "综合所有结论给出最终根因裁决与处置建议",
            "VerificationAgent": "基于最终裁决生成功能/性能/回归/回滚验证计划",
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
                        "use_tool": None,
                        "database_tables": [],
                        "api_endpoints": [],
                        "service_names": [],
                        "code_artifacts": [],
                        "class_names": [],
                        "monitor_items": [],
                        "dependency_services": [],
                        "trace_ids": [],
                        "error_keywords": [],
                        "skill_hints": [],
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
                        "use_tool": None,
                        "database_tables": [],
                        "api_endpoints": [],
                        "service_names": [],
                        "code_artifacts": [],
                        "class_names": [],
                        "monitor_items": [],
                        "dependency_services": [],
                        "trace_ids": [],
                        "error_keywords": [],
                        "skill_hints": [],
                    }
        return commands

    @staticmethod
    def _normalize_text_items(value: Any, *, limit: int = 20, width: int = 160) -> List[str]:
        """把任意输入清洗成稳定的文本列表。"""
        if not isinstance(value, list):
            return []
        picks: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            picks.append(text[:width])
        return list(dict.fromkeys(picks))[:limit]

    @staticmethod
    def _normalize_database_tables(value: Any) -> List[str]:
        """把数据库表线索清洗成统一的表名列表。"""
        return LangGraphRuntimeOrchestrator._normalize_text_items(value, limit=20, width=120)

    def _normalize_investigation_leads(self, compact_context: Dict[str, Any]) -> Dict[str, Any]:
        """把 investigation leads 归一化成统一字段结构。"""
        leads = compact_context.get("investigation_leads") if isinstance(compact_context, dict) else {}
        if not isinstance(leads, dict):
            leads = {}
        return {
            "api_endpoints": self._normalize_text_items(leads.get("api_endpoints"), limit=12, width=180),
            "service_names": self._normalize_text_items(leads.get("service_names"), limit=12, width=120),
            "code_artifacts": self._normalize_text_items(leads.get("code_artifacts"), limit=16, width=180),
            "class_names": self._normalize_text_items(leads.get("class_names"), limit=16, width=120),
            "database_tables": self._normalize_database_tables(leads.get("database_tables")),
            "monitor_items": self._normalize_text_items(leads.get("monitor_items"), limit=16, width=160),
            "dependency_services": self._normalize_text_items(leads.get("dependency_services"), limit=16, width=120),
            "trace_ids": self._normalize_text_items(leads.get("trace_ids"), limit=8, width=120),
            "error_keywords": self._normalize_text_items(leads.get("error_keywords"), limit=12, width=120),
            "domain": str(leads.get("domain") or "").strip(),
            "aggregate": str(leads.get("aggregate") or "").strip(),
            "owner_team": str(leads.get("owner_team") or "").strip(),
            "owner": str(leads.get("owner") or "").strip(),
        }

    def _enrich_agent_commands_with_asset_mapping(
        self,
        commands: Dict[str, Dict[str, Any]],
        compact_context: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """把责任田映射出的结构化线索补到各 Agent 命令里。"""
        if not isinstance(commands, dict):
            return {}
        leads = self._normalize_investigation_leads(compact_context)
        interface_mapping = compact_context.get("interface_mapping") if isinstance(compact_context, dict) else {}
        if not isinstance(interface_mapping, dict):
            interface_mapping = {}
        if not leads.get("database_tables"):
            leads["database_tables"] = self._normalize_database_tables(
                interface_mapping.get("database_tables") or interface_mapping.get("db_tables") or []
            )
        endpoint = interface_mapping.get("endpoint") if isinstance(interface_mapping.get("endpoint"), dict) else {}
        if not leads.get("api_endpoints"):
            endpoint_label = " ".join(
                part for part in [str(endpoint.get("method") or "").strip(), str(endpoint.get("path") or "").strip()] if part
            ).strip()
            if endpoint_label:
                leads["api_endpoints"] = [endpoint_label]
        if not leads.get("service_names"):
            service_name = str(endpoint.get("service") or "").strip()
            if service_name:
                leads["service_names"] = [service_name]
        if not any(
            leads.get(key)
            for key in (
                "api_endpoints",
                "service_names",
                "code_artifacts",
                "class_names",
                "database_tables",
                "monitor_items",
                "dependency_services",
                "trace_ids",
                "error_keywords",
            )
        ):
            return commands

        def _merge_values(cmd: Dict[str, Any], field: str, values: List[str], *, limit: int = 20) -> None:
            """按字段合并新旧线索值，并保持稳定去重顺序。"""
            existing = self._normalize_text_items(cmd.get(field), limit=limit, width=180)
            if field == "database_tables":
                existing = self._normalize_database_tables(cmd.get(field))
            cmd[field] = list(dict.fromkeys(existing + list(values or [])))[:limit]

        def _requires_tool(target: str, cmd: Dict[str, Any]) -> bool:
            """关键证据 Agent 在命中结构化线索时必须保留工具检索能力。"""
            if target == "LogAgent":
                return bool(
                    cmd.get("api_endpoints")
                    or cmd.get("trace_ids")
                    or cmd.get("error_keywords")
                    or cmd.get("service_names")
                )
            if target == "CodeAgent":
                return bool(
                    cmd.get("class_names")
                    or cmd.get("code_artifacts")
                    or cmd.get("api_endpoints")
                    or cmd.get("service_names")
                )
            if target == "DatabaseAgent":
                return bool(cmd.get("database_tables"))
            if target == "ChangeAgent":
                return bool(cmd.get("service_names") or cmd.get("code_artifacts"))
            return False

        for target, base in list(commands.items()):
            if not isinstance(base, dict):
                continue
            cmd = dict(base)
            for field, limit in (
                ("api_endpoints", 12),
                ("service_names", 12),
                ("code_artifacts", 16),
                ("class_names", 16),
                ("database_tables", 20),
                ("monitor_items", 16),
                ("dependency_services", 16),
                ("trace_ids", 8),
                ("error_keywords", 12),
            ):
                values = leads.get(field)
                if isinstance(values, list) and values:
                    _merge_values(cmd, field, values, limit=limit)

            if target == "LogAgent":
                if not str(cmd.get("focus") or "").strip():
                    focus_bits = []
                    if cmd.get("api_endpoints"):
                        focus_bits.append(f"围绕接口调用链: {', '.join(cmd['api_endpoints'][:2])}")
                    if cmd.get("trace_ids"):
                        focus_bits.append(f"追踪 Trace: {', '.join(cmd['trace_ids'][:3])}")
                    if cmd.get("error_keywords"):
                        focus_bits.append(f"异常关键词: {', '.join(cmd['error_keywords'][:4])}")
                    cmd["focus"] = "；".join(focus_bits)
                if not str(cmd.get("expected_output") or "").strip():
                    cmd["expected_output"] = "输出接口/Trace 维度的错误时间线、关键日志片段、上下游异常链路"
            elif target == "DomainAgent":
                if not str(cmd.get("focus") or "").strip():
                    focus_bits = []
                    if cmd.get("api_endpoints"):
                        focus_bits.append(f"确认接口归属: {', '.join(cmd['api_endpoints'][:2])}")
                    if leads.get("domain") or leads.get("aggregate"):
                        focus_bits.append(f"领域/聚合根: {leads.get('domain') or '-'} / {leads.get('aggregate') or '-'}")
                    if cmd.get("dependency_services"):
                        focus_bits.append(f"下游服务: {', '.join(cmd['dependency_services'][:4])}")
                    cmd["focus"] = "；".join(focus_bits)
                if not str(cmd.get("expected_output") or "").strip():
                    cmd["expected_output"] = "输出责任田归属、业务链路、上下游依赖与责任团队判断"
            elif target == "CodeAgent":
                if not str(cmd.get("focus") or "").strip():
                    focus_bits = []
                    if cmd.get("class_names"):
                        focus_bits.append(f"类名检索: {', '.join(cmd['class_names'][:4])}")
                    if cmd.get("code_artifacts"):
                        focus_bits.append(f"代码线索: {', '.join(cmd['code_artifacts'][:4])}")
                    if cmd.get("api_endpoints"):
                        focus_bits.append(f"接口入口: {', '.join(cmd['api_endpoints'][:2])}")
                    cmd["focus"] = "；".join(focus_bits)
                if not str(cmd.get("expected_output") or "").strip():
                    cmd["expected_output"] = "输出相关代码文件、入口类/服务类、可疑调用链与回归风险点"
            elif target == "DatabaseAgent":
                if not str(cmd.get("focus") or "").strip():
                    cmd["focus"] = f"优先检查责任田映射表: {', '.join((cmd.get('database_tables') or [])[:8])}"
                if not str(cmd.get("expected_output") or "").strip():
                    cmd["expected_output"] = "输出各目标表的 Meta、索引、疑似慢 SQL 与会话阻塞信号"
            elif target == "MetricsAgent":
                if not str(cmd.get("focus") or "").strip():
                    focus_bits = []
                    if cmd.get("monitor_items"):
                        focus_bits.append(f"监控项: {', '.join(cmd['monitor_items'][:4])}")
                    if cmd.get("service_names"):
                        focus_bits.append(f"服务: {', '.join(cmd['service_names'][:4])}")
                    if cmd.get("api_endpoints"):
                        focus_bits.append(f"接口: {', '.join(cmd['api_endpoints'][:2])}")
                    cmd["focus"] = "；".join(focus_bits)
                if not str(cmd.get("expected_output") or "").strip():
                    cmd["expected_output"] = "输出异常指标窗口、阈值变化、接口与资源信号的相关性"
            elif target == "ChangeAgent":
                if not str(cmd.get("focus") or "").strip():
                    focus_bits = []
                    if cmd.get("service_names"):
                        focus_bits.append(f"服务变更: {', '.join(cmd['service_names'][:4])}")
                    if cmd.get("code_artifacts"):
                        focus_bits.append(f"代码路径: {', '.join(cmd['code_artifacts'][:4])}")
                    cmd["focus"] = "；".join(focus_bits)
                if not str(cmd.get("expected_output") or "").strip():
                    cmd["expected_output"] = "输出故障窗口前后的发布、提交与配置变化候选"
            elif target == "RunbookAgent":
                if not str(cmd.get("focus") or "").strip():
                    focus_bits = []
                    if leads.get("domain") or leads.get("aggregate"):
                        focus_bits.append(f"领域/聚合根: {leads.get('domain') or '-'} / {leads.get('aggregate') or '-'}")
                    if cmd.get("api_endpoints"):
                        focus_bits.append(f"接口: {', '.join(cmd['api_endpoints'][:2])}")
                    if cmd.get("error_keywords"):
                        focus_bits.append(f"故障模式: {', '.join(cmd['error_keywords'][:4])}")
                    cmd["focus"] = "；".join(focus_bits)
                if not str(cmd.get("expected_output") or "").strip():
                    cmd["expected_output"] = "输出匹配的 SOP、相似案例、止血动作与验证步骤"

            # 对关键证据型 Agent，如果责任田已经给出了可检索线索，就不允许 commander 在这里把工具关掉。
            if _requires_tool(target, cmd):
                cmd["use_tool"] = True
                cmd["tool_requirement"] = "required_by_investigation_leads"
            commands[target] = cmd
        return commands

    def _enrich_agent_commands_with_skill_hints(
        self,
        commands: Dict[str, Dict[str, Any]],
        compact_context: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """把 skill 产生的提示语补到各 Agent 命令里。"""
        if not isinstance(commands, dict):
            return {}

        incident = compact_context.get("incident") if isinstance(compact_context, dict) else {}
        incident_text = " ".join(
            [
                str((incident or {}).get("title") or ""),
                str((incident or {}).get("description") or ""),
                str(compact_context.get("log_excerpt") or ""),
            ]
        ).lower()
        has_db_signal = any(
            token in incident_text
            for token in ("sql", "数据库", "连接池", "hikari", "lock", "slow", "deadlock", "session")
        )
        has_route_signal = any(token in incident_text for token in ("404", "route", "路由", "not found", "网关"))

        default_skill_by_agent: Dict[str, List[str]] = {
            "ProblemAnalysisAgent": ["incident-commander"],
            "LogAgent": ["log-forensics"],
            "DomainAgent": ["domain-responsibility-mapping"],
            "CodeAgent": ["code-path-analysis"],
            "DatabaseAgent": ["db-bottleneck-diagnosis"] if has_db_signal else [],
            "MetricsAgent": ["metrics-anomaly-triage"],
            "ChangeAgent": ["change-correlation-review"],
            "RunbookAgent": ["runbook-execution-planner"],
            "RuleSuggestionAgent": ["alert-rule-hardening"],
            "CriticAgent": ["architectural-critique"],
            "RebuttalAgent": ["evidence-rebuttal"],
            "JudgeAgent": (
                ["final-judgment-synthesis", "db-bottleneck-diagnosis"]
                if has_db_signal
                else ["final-judgment-synthesis"]
            ),
            "VerificationAgent": ["verification-plan-builder"],
        }
        if has_route_signal:
            default_skill_by_agent.setdefault("DomainAgent", []).append("domain-responsibility-mapping")
            default_skill_by_agent.setdefault("CodeAgent", []).append("code-path-analysis")
            default_skill_by_agent.setdefault("CriticAgent", []).append("architectural-critique")

        def _normalize_hints(value: Any) -> List[str]:
            """把候选提示语清洗成适合注入命令的数组。"""
            if not isinstance(value, list):
                return []
            picks: List[str] = []
            for item in value:
                text = str(item or "").strip()
                if not text:
                    continue
                picks.append(text[:80])
            return list(dict.fromkeys(picks))[:8]

        for target, cmd in list(commands.items()):
            if not isinstance(cmd, dict):
                continue
            existing = _normalize_hints(cmd.get("skill_hints"))
            if existing:
                cmd["skill_hints"] = existing
                commands[target] = cmd
                continue
            fallback = list(default_skill_by_agent.get(target) or [])
            cmd["skill_hints"] = list(dict.fromkeys([str(item).strip() for item in fallback if str(item).strip()]))[:8]
            commands[target] = cmd
        return commands

    async def _run_problem_analysis_commander(
        self,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        运行主 Agent 的“任务分发”阶段。

        这里的职责不是给出最终根因，而是：
        1. 先向前端发一条主 Agent 开场消息。
        2. 构造 commander prompt，让模型生成专家分工方案。
        3. 记录本轮 turn，并把输出解析成标准化 agent commands。
        4. 再把责任田映射与默认 skill hints 注入命令，供后续专家执行。
        """
        spec = self._problem_analysis_agent_spec()
        round_number = len(self.turns) + 1
        # 这条消息只是给用户一个“主 Agent 已开始拆解问题”的可见锚点，
        # 真正的命令内容仍以后续结构化 payload 为准。
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
            existing_agent_outputs=existing_agent_outputs,
        )
        # commander 结果必须先落成 turn，再做命令提取；这样前端轨迹和审计链路
        # 才能解释“为什么会下发这些命令”。
        turn = await self._agent_runner.run_agent(
            spec=spec,
            prompt=prompt,
            round_number=round_number,
            loop_round=loop_round,
            history_cards_context=history_cards,
        )
        await self._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)

        payload = turn.output_content if isinstance(turn.output_content, dict) else {}
        # 命令提取后还会追加两层系统增强：
        # 1. 责任田映射出的接口、表名、类名等调查线索
        # 2. 针对不同 Agent 的默认 skill hints
        commands = self._extract_agent_commands_from_payload(payload, fill_defaults=True)
        commands = self._enrich_agent_commands_with_asset_mapping(commands, compact_context)
        commands = self._enrich_agent_commands_with_skill_hints(commands, compact_context)
        return {
            "commands": commands,
            "next_mode": str(payload.get("next_mode") or "").strip().lower(),
            "next_agent": str(payload.get("next_agent") or "").strip(),
            "should_stop": bool(payload.get("should_stop") or False),
            "stop_reason": str(payload.get("stop_reason") or "").strip(),
            "should_pause_for_review": bool(payload.get("should_pause_for_review") or False),
            "review_reason": str(payload.get("review_reason") or "").strip(),
            "review_payload": payload.get("review_payload") if isinstance(payload.get("review_payload"), dict) else {},
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
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        运行主 Agent 的监督路由阶段。

        当一轮并行分析结束后，这里负责判断：
        - 是继续拉起新的专家补证
        - 还是进入 Judge / finalize
        - 还是触发人工审核暂停
        """
        spec = self._problem_analysis_agent_spec()
        round_number = len(self.turns) + 1
        # Avoid repetitive commander placeholder messages on every supervisor step.
        # Emit once near round start to keep UI concise and reduce "looping" perception.
        if int(discussion_step_count or 0) <= 1:
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
            existing_agent_outputs=existing_agent_outputs,
        )
        turn = await self._agent_runner.run_agent(
            spec=spec,
            prompt=prompt,
            round_number=round_number,
            loop_round=loop_round,
            history_cards_context=history_cards,
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
        commands = self._enrich_agent_commands_with_asset_mapping(commands, compact_context)
        commands = self._enrich_agent_commands_with_skill_hints(commands, compact_context)
        return {
            "commands": commands,
            "next_mode": next_mode,
            "next_agent": next_agent,
            "should_stop": bool(payload.get("should_stop") or False),
            "stop_reason": str(payload.get("stop_reason") or "").strip(),
            "should_pause_for_review": bool(payload.get("should_pause_for_review") or False),
            "review_reason": str(payload.get("review_reason") or "").strip(),
            "review_payload": payload.get("review_payload") if isinstance(payload.get("review_payload"), dict) else {},
        }

    async def _emit_agent_command_issued(
        self,
        commander: str,
        target: str,
        loop_round: int,
        round_number: int,
        command: Dict[str, Any],
    ) -> None:
        """执行发射Agentcommandissued，并同步更新运行时状态、持久化结果或审计轨迹。"""
        command_text = str(command.get("task") or "").strip() or f"请完成 {target} 维度分析"
        focus = str(command.get("focus") or "").strip()
        expected = str(command.get("expected_output") or "").strip()
        use_tool = command.get("use_tool")
        database_tables = self._normalize_database_tables(command.get("database_tables"))
        api_endpoints = self._normalize_text_items(command.get("api_endpoints"), limit=12, width=180)
        service_names = self._normalize_text_items(command.get("service_names"), limit=12, width=120)
        code_artifacts = self._normalize_text_items(command.get("code_artifacts"), limit=16, width=180)
        class_names = self._normalize_text_items(command.get("class_names"), limit=16, width=120)
        monitor_items = self._normalize_text_items(command.get("monitor_items"), limit=16, width=160)
        dependency_services = self._normalize_text_items(command.get("dependency_services"), limit=16, width=120)
        trace_ids = self._normalize_text_items(command.get("trace_ids"), limit=8, width=120)
        error_keywords = self._normalize_text_items(command.get("error_keywords"), limit=12, width=120)
        message_parts = [f"{commander} 指令 {target}: {command_text}"]
        if focus:
            message_parts.append(f"重点: {focus}")
        if expected:
            message_parts.append(f"输出: {expected}")
        if api_endpoints:
            message_parts.append(f"接口: {', '.join(api_endpoints[:3])}")
        if service_names:
            message_parts.append(f"服务: {', '.join(service_names[:4])}")
        if class_names:
            message_parts.append(f"类名: {', '.join(class_names[:4])}")
        if code_artifacts:
            message_parts.append(f"代码线索: {', '.join(code_artifacts[:4])}")
        if database_tables:
            message_parts.append(f"目标表: {', '.join(database_tables[:8])}")
        if monitor_items:
            message_parts.append(f"监控项: {', '.join(monitor_items[:4])}")
        if dependency_services:
            message_parts.append(f"依赖服务: {', '.join(dependency_services[:4])}")
        if trace_ids:
            message_parts.append(f"Trace: {', '.join(trace_ids[:3])}")
        if error_keywords:
            message_parts.append(f"异常关键词: {', '.join(error_keywords[:4])}")
        if isinstance(use_tool, bool):
            message_parts.append(f"工具调用: {'允许' if use_tool else '禁止'}")
        agent_message = AgentMessage(
            sender=commander,
            receiver=target,
            message_type="command",
            content={
                "task": command_text,
                "focus": focus,
                "expected_output": expected,
                "use_tool": use_tool,
                "database_tables": database_tables,
                "api_endpoints": api_endpoints,
                "service_names": service_names,
                "code_artifacts": code_artifacts,
                "class_names": class_names,
                "monitor_items": monitor_items,
                "dependency_services": dependency_services,
                "trace_ids": trace_ids,
                "error_keywords": error_keywords,
            },
        )
        await self._emit_event(
            {
                "type": "agent_command_issued",
                "phase": "orchestration",
                "agent_name": commander,
                "target_agent": target,
                "loop_round": loop_round,
                "round_number": round_number,
                "command": command_text,
                "use_tool": use_tool,
                "database_tables": database_tables,
                "api_endpoints": api_endpoints,
                "service_names": service_names,
                "code_artifacts": code_artifacts,
                "class_names": class_names,
                "monitor_items": monitor_items,
                "dependency_services": dependency_services,
                "trace_ids": trace_ids,
                "error_keywords": error_keywords,
                "message": "\n".join(message_parts),
                "agent_message": agent_message.model_dump(mode="json"),
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
        """执行发射Agentcommandfeedback，并同步更新运行时状态、持久化结果或审计轨迹。"""
        output = turn.output_content if isinstance(turn.output_content, dict) else {}
        feedback_text = str(output.get("chat_message") or output.get("conclusion") or "")[:300]
        degraded = bool(output.get("degraded"))
        evidence_status = str(output.get("evidence_status") or ("degraded" if degraded else "collected")).strip() or "collected"
        tool_status = str(output.get("tool_status") or "").strip()
        degrade_reason = str(output.get("degrade_reason") or "").strip()
        agent_message = AgentMessage(
            sender=source,
            receiver="ProblemAnalysisAgent",
            message_type="feedback",
            content={
                "command": str(command.get("task") or "")[:240],
                "feedback": feedback_text,
                "confidence": float(turn.confidence or 0.0),
                "degraded": degraded,
                "evidence_status": evidence_status,
                "tool_status": tool_status,
                "degrade_reason": degrade_reason,
            },
        )
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
                "message": f"{source} 已提交降级反馈" if degraded else f"{source} 已执行主Agent命令并提交结论",
                "agent_message": agent_message.model_dump(mode="json"),
                "session_id": self.session_id,
                "confidence": float(turn.confidence or 0.0),
                "degraded": degraded,
                "evidence_status": evidence_status,
                "tool_status": tool_status,
                "degrade_reason": degrade_reason,
            }
        )

    async def _emit_problem_analysis_final_summary(
        self,
        loop_round: int,
        history_cards: Optional[List[AgentEvidence]] = None,
    ) -> None:
        """执行发射problem分析final摘要，并同步更新运行时状态、持久化结果或审计轨迹。"""
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
        agent_mailbox: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        """
        把并行分析阶段委托给 `PhaseExecutor`。

        当前 orchestrator 只保留阶段入口和上下文拼装职责，真正的批次拆分、
        并发控制、优先级调度和失败降级都下沉到 `PhaseExecutor` 内部。
        """
        await self._phase_executor.run_parallel_analysis_phase(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=agent_commands,
            dialogue_items=dialogue_items,
            agent_mailbox=agent_mailbox,
        )

    async def _run_collaboration_phase(
        self,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        agent_mailbox: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        """把专家协作阶段委托给 `PhaseExecutor` 统一执行。"""
        await self._phase_executor.run_collaboration_phase(
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            dialogue_items=dialogue_items,
            agent_mailbox=agent_mailbox,
        )

    async def _graph_finalize(self, state: _DebateExecState) -> _DebateExecState:
        """
        执行图收尾阶段。

        这里统一处理三类收尾：
        1. 正常完成，输出 final payload
        2. 命中人工审核，进入 waiting_review
        3. 其他异常或缺口场景下的兜底收口，确保会话进入明确终态
        """
        history_cards = self._history_cards_for_state(state, limit=24)
        consensus_reached = bool(state.get("consensus_reached") or False)
        executed_rounds = int(state.get("executed_rounds") or state.get("current_round") or 0)
        awaiting_human_review = bool(state.get("awaiting_human_review") or False)
        human_review_reason = str(state.get("human_review_reason") or "").strip()
        human_review_payload = dict(state.get("human_review_payload") or {})
        resume_from_step = str(state.get("resume_from_step") or "report_generation").strip()
        final_payload = dict(state.get("final_payload") or {})
        if not final_payload:
            # finalize 是最后一道兜底门。即便中间节点没有显式写入 final_payload，
            # 这里也必须补出完整结果对象，避免前端和报告页拿到空结果。
            final_payload = self._build_final_payload(
                history_cards=history_cards,
                consensus_reached=consensus_reached,
                executed_rounds=executed_rounds,
            )
        if awaiting_human_review:
            final_payload["awaiting_human_review"] = True
            final_payload["human_review"] = {
                "reason": human_review_reason,
                "payload": human_review_payload,
                "resume_from_step": resume_from_step,
            }
            await runtime_session_store.mark_waiting_review(
                str(self.session_id),
                FinalVerdict.model_validate(final_payload.get("final_judgment") or {}),
            )
            await self._emit_event(
                {
                    "type": "runtime_human_review_requested",
                    "confidence": final_payload.get("confidence", 0.0),
                    "consensus_reached": consensus_reached,
                    "mode": "langgraph_runtime",
                    "review_reason": human_review_reason,
                    "resume_from_step": resume_from_step,
                }
            )
        else:
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
        next_state = {"final_payload": final_payload}
        merged_preview = {**dict(state), **next_state}
        return {**next_state, **structured_state_snapshot(merged_preview)}

    def _build_peer_driven_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """组装 peer-driven 协作 Prompt。"""
        return self._prompt_builder.build_peer_driven_prompt(
            spec=spec,
            loop_round=loop_round,
            context=context,
            history_cards=history_cards,
            assigned_command=assigned_command,
            work_log_context=self._work_log_context(limit=14),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
        )

    def _collect_peer_items_from_dialogue(
        self,
        dialogue_items: List[Dict[str, Any]],
        exclude_agent: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        # compatibility shim: moved to context_builders.collect_peer_items_from_dialogue
        """从对话流中抽取可复用的同伴结论条目。"""
        return collect_peer_items_from_dialogue_ctx(
            dialogue_items=dialogue_items,
            exclude_agent=exclude_agent,
            limit=limit,
        )

    def _collect_peer_items(
        self,
        history_cards: List[AgentEvidence],
        exclude_agent: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        # compatibility shim: moved to context_builders.collect_peer_items_from_cards
        """聚合历史卡片和对话摘要，形成协作阶段的 peer items。"""
        return collect_peer_items_from_cards_ctx(
            history_cards=history_cards,
            exclude_agent=exclude_agent,
            limit=limit,
        )

    def _judge_output_schema(self) -> Dict[str, Any]:
        """返回 JudgeAgent 的结构化输出 Schema。"""
        return judge_output_schema_template()

    def _latest_cards_for_agents(
        self,
        history_cards: List[AgentEvidence],
        agent_names: List[str],
        limit: int,
    ) -> List[AgentEvidence]:
        """返回指定 Agent 最近若干张卡片，供 Prompt 和路由复用。"""
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
        """构造通用降级 turn，表示本轮执行未拿到完整结果。"""
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
        fallback_output["degraded"] = True
        fallback_output["degrade_reason"] = friendly_reason
        fallback_output["evidence_status"] = "degraded"
        fallback_output["tool_status"] = "unknown"
        fallback_output["next_checks"] = list(
            dict.fromkeys(
                [
                    *list(fallback_output.get("next_checks") or []),
                    f"重试 {spec.name} 并重新采集关键证据",
                ]
            )
        )[:6]
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

    async def _create_missing_evidence_turn(
        self,
        *,
        spec: AgentSpec,
        prompt: str,
        round_number: int,
        loop_round: int,
        tool_name: str,
        tool_status: str,
        reason: str,
    ) -> DebateTurn:
        """构造关键证据缺失时的受限分析 turn。"""
        await self._emit_event(
            {
                "type": "agent_round_skipped",
                "phase": spec.phase,
                "agent_name": spec.name,
                "agent_role": spec.role,
                "loop_round": loop_round,
                "round_number": round_number,
                "reason": reason,
                "skip_mode": "tool_unavailable",
                "tool_name": tool_name,
                "tool_status": tool_status,
                "session_id": self.session_id,
            }
        )
        status_text = tool_status or "unavailable"
        analysis = (
            f"{spec.name} 需要依赖 {tool_name or '关键工具'} 采集实时证据，但当前工具状态为 {status_text}，"
            "本轮未完成真实证据检索。"
        )
        payload = {
            "chat_message": f"我收到了排查命令，但 {tool_name or '关键工具'} 当前{status_text}，只能先标记证据缺失。",
            "analysis": analysis,
            "conclusion": f"{spec.name} 证据未采集完成：{reason}",
            "evidence_chain": [],
            "counter_evidence": [],
            "next_checks": [f"恢复 {tool_name or '对应工具'} 后重试 {spec.name}"],
            "confidence": 0.22,
            "degraded": True,
            "degrade_reason": reason,
            "evidence_status": "missing",
            "tool_status": status_text,
            "tool_name": tool_name,
            "raw_text": analysis[:1200],
        }
        now = datetime.utcnow()
        return DebateTurn(
            round_number=round_number,
            phase=spec.phase,
            agent_name=spec.name,
            agent_role=spec.role,
            model={"name": settings.llm_model},
            input_message=prompt,
            output_content=payload,
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            started_at=now,
            completed_at=now,
        )

    @staticmethod
    def _friendly_degrade_reason(error_text: str) -> str:
        """把内部降级原因转换成前端可读的说明文案。"""
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
        """抓取当前 state 的历史卡片快照，避免后续逻辑误读可变对象。"""
        cards: List[AgentEvidence] = []
        for turn in self.turns[-max(1, limit) :]:
            output = turn.output_content if isinstance(turn.output_content, dict) else {}
            cards.append(
                AgentEvidence(
                    agent_name=turn.agent_name,
                    phase=turn.phase,
                    summary=str(output.get("analysis") or "")[:200],
                    conclusion=str(output.get("conclusion") or "")[:220],
                    evidence_chain=self._evidence_texts(output.get("evidence_chain"), limit=3),
                    confidence=float(turn.confidence or 0.0),
                    raw_output=output,
                )
            )
        return cards

    @staticmethod
    def _is_degraded_output(payload: Any) -> bool:
        """判断某个输出是否属于降级或受限分析结果。"""
        if not isinstance(payload, dict):
            return False
        if bool(payload.get("degraded")):
            return True
        evidence_status = str(payload.get("evidence_status") or "").strip().lower()
        if evidence_status in {"degraded", "missing", "inferred_without_tool"}:
            return True
        conclusion = str(payload.get("conclusion") or "").strip().lower()
        return "调用超时，已降级继续" in conclusion or "调用异常，已降级继续" in conclusion

    @staticmethod
    def _tool_limited_status(
        *,
        spec: AgentSpec,
        assigned_command: Optional[Dict[str, Any]],
        context_with_tools: Dict[str, Any],
    ) -> Optional[Dict[str, str]]:
        """提取工具受限状态，供质量门禁和前端提示复用。"""
        if spec.name not in LangGraphRuntimeOrchestrator.KEY_EVIDENCE_AGENTS:
            return None
        if not isinstance(assigned_command, dict) or not assigned_command:
            return None
        tool_ctx = context_with_tools.get("tool_context")
        if not isinstance(tool_ctx, dict):
            return None
        command_gate = tool_ctx.get("command_gate")
        if not isinstance(command_gate, dict):
            command_gate = {}
        if not bool(command_gate.get("has_command")) or not bool(command_gate.get("allow_tool")):
            return None
        status = str(tool_ctx.get("status") or "").strip().lower()
        used = bool(tool_ctx.get("used"))
        if used and status == "ok":
            return None
        if status not in {"disabled", "unavailable", "error", "failed", "timeout"}:
            return None
        summary = str(tool_ctx.get("summary") or "").strip()
        tool_name = str(tool_ctx.get("name") or "").strip()
        reason = summary or str(command_gate.get("reason") or "").strip() or f"{tool_name or '关键工具'} 当前不可用"
        return {
            "tool_name": tool_name,
            "tool_status": status,
            "reason": reason,
        }

    def _collect_missing_leads_for_agent(
        self,
        *,
        agent_name: str,
        context_with_tools: Dict[str, Any],
    ) -> List[str]:
        """收集当前 Agent 还缺失的关键调查线索。"""
        leads = context_with_tools.get("investigation_leads")
        if not isinstance(leads, dict):
            tool_ctx = context_with_tools.get("tool_context")
            data = tool_ctx.get("data") if isinstance(tool_ctx, dict) else None
            leads = data.get("investigation_leads") if isinstance(data, dict) else {}
        if not isinstance(leads, dict):
            leads = {}
        key_map = {
            "LogAgent": ("api_endpoints", "trace_ids", "error_keywords"),
            "CodeAgent": ("class_names", "code_artifacts", "api_endpoints", "service_names"),
            "DatabaseAgent": ("database_tables", "api_endpoints", "service_names"),
            "MetricsAgent": ("monitor_items", "service_names", "api_endpoints"),
        }
        values: List[str] = []
        for key in key_map.get(agent_name, ()):
            raw_items = leads.get(key)
            if not isinstance(raw_items, list):
                continue
            for item in raw_items[:3]:
                text = str(item or "").strip()
                if text:
                    values.append(text[:140])
        deduped = list(dict.fromkeys(values))
        return deduped[:4]

    def _apply_tool_limited_semantics(
        self,
        *,
        turn: DebateTurn,
        spec: AgentSpec,
        assigned_command: Optional[Dict[str, Any]],
        context_with_tools: Dict[str, Any],
    ) -> DebateTurn:
        """把工具受限语义补到输出里，供前端和 Judge 正确识别。"""
        limited = self._tool_limited_status(
            spec=spec,
            assigned_command=assigned_command,
            context_with_tools=context_with_tools,
        )
        if limited is None:
            return turn
        payload = dict(turn.output_content or {})
        tool_name = limited["tool_name"]
        tool_status = limited["tool_status"]
        reason = limited["reason"]
        missing_leads = self._collect_missing_leads_for_agent(
            agent_name=spec.name,
            context_with_tools=context_with_tools,
        )
        existing_missing = payload.get("missing_info")
        missing_info = list(existing_missing) if isinstance(existing_missing, list) else []
        if tool_name:
            missing_info.append(f"{tool_name} 实时取证结果")
        missing_info.extend(missing_leads)
        next_checks = payload.get("next_checks")
        if not isinstance(next_checks, list):
            next_checks = []
        next_checks = list(next_checks)
        next_checks.extend(
            [
                f"恢复 {tool_name or '关键工具'} 后补采 {spec.name} 所需证据",
                f"复核 {spec.name} 当前基于已有证据得出的受限结论",
            ]
        )
        analysis = str(payload.get("analysis") or "").strip()
        conclusion = str(payload.get("conclusion") or "").strip()
        chat_message = str(payload.get("chat_message") or "").strip()
        if analysis:
            analysis = f"{analysis}\n\n受限分析说明：{reason}。本结论仅基于当前已有证据推理，未包含实时工具取证结果。"
        else:
            analysis = f"{spec.name} 当前无法使用 {tool_name or '关键工具'} 进行实时取证，已基于已有证据完成受限分析。限制原因：{reason}。"
        if conclusion:
            conclusion = f"{conclusion}（受限分析：{tool_name or '关键工具'} {tool_status}）"
        else:
            conclusion = f"{spec.name} 基于已有证据给出受限分析结论，但 {tool_name or '关键工具'} 当前{tool_status}。"
        if chat_message:
            chat_message = f"{chat_message} 当前工具不可用，我先基于已有证据给出受限判断。"
        else:
            chat_message = f"{tool_name or '关键工具'} 当前{tool_status}，我先基于已有证据给出受限分析。"
        confidence = float(payload.get("confidence", turn.confidence) or turn.confidence or 0.0)
        confidence = min(confidence, 0.58)
        confidence = max(confidence, 0.18)
        payload.update(
            {
                "chat_message": chat_message,
                "analysis": analysis,
                "conclusion": conclusion,
                "confidence": confidence,
                "degraded": True,
                "degrade_reason": reason,
                "evidence_status": "inferred_without_tool",
                "tool_status": tool_status,
                "tool_name": tool_name,
                "missing_info": list(dict.fromkeys(str(item).strip() for item in missing_info if str(item).strip()))[:6],
                "next_checks": list(dict.fromkeys(str(item).strip() for item in next_checks if str(item).strip()))[:6],
            }
        )
        return replace(turn, output_content=payload, confidence=confidence)

    @staticmethod
    def _count_key_evidence_coverage(history_cards: List[AgentEvidence]) -> Dict[str, int]:
        """计算统计keyevidencecoverage，为治理、裁决或展示提供量化依据。"""
        coverage = {"ok": 0, "degraded": 0, "missing": 0}
        seen: set[str] = set()
        for card in history_cards:
            name = str(card.agent_name or "").strip()
            if name not in LangGraphRuntimeOrchestrator.KEY_EVIDENCE_AGENTS or name in seen:
                continue
            seen.add(name)
            output = card.raw_output if isinstance(getattr(card, "raw_output", None), dict) else {}
            evidence_status = str(output.get("evidence_status") or "").strip().lower()
            if evidence_status == "missing":
                coverage["missing"] += 1
            elif LangGraphRuntimeOrchestrator._is_degraded_output(output):
                coverage["degraded"] += 1
            else:
                coverage["ok"] += 1
        return coverage

    def _infer_reply_target(
        self,
        spec_name: str,
        history_cards: List[AgentEvidence],
    ) -> Optional[str]:
        """从消息或输出结构里推断 reply_to 的目标 Agent。"""
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
        """执行记录turn，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self.turns.append(turn)
        card = AgentEvidence(
            agent_name=turn.agent_name,
            phase=turn.phase,
            summary=str(turn.output_content.get("analysis") or "")[:200],
            conclusion=str(turn.output_content.get("conclusion") or "")[:220],
            evidence_chain=self._evidence_texts(turn.output_content.get("evidence_chain"), limit=3),
            confidence=float(turn.confidence or 0.0),
            raw_output=turn.output_content,
        )
        history_cards.append(card)
        pruned_cards, prune_stats = prune_history_cards_ops(history_cards, limit=20)
        history_cards[:] = pruned_cards
        if int(prune_stats.get("pruned_count") or 0) > 0:
            await self._emit_event(
                {
                    "type": "history_pruned",
                    "phase": turn.phase,
                    "agent_name": turn.agent_name,
                    "loop_round": loop_round,
                    "round_number": turn.round_number,
                    "pruned_count": int(prune_stats.get("pruned_count") or 0),
                    "saved_chars": int(prune_stats.get("saved_chars") or 0),
                }
            )

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
        """返回当前部署配置下启用的 Agent 执行顺序。"""
        return build_agent_sequence(enable_critique=bool(self._enable_critique))

    def _evidence_texts(self, raw_items: Any, *, limit: int = 3) -> List[str]:
        """从历史卡片中抽取可直接放入 Prompt 的证据文本。"""
        if not isinstance(raw_items, list):
            return []
        texts: List[str] = []
        for item in raw_items[: max(1, limit)]:
            if isinstance(item, dict):
                description = str(item.get("description") or item.get("evidence") or item.get("summary") or "").strip()
                if description:
                    texts.append(description[:220])
                continue
            text = str(item or "").strip()
            if text:
                texts.append(text[:220])
        return texts

    def _build_agent_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """组装单个专家 Agent 的执行 Prompt。"""
        return self._prompt_builder.build_agent_prompt(
            spec=spec,
            loop_round=loop_round,
            context=context,
            history_cards=history_cards,
            assigned_command=assigned_command,
            work_log_context=self._work_log_context(limit=14),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
        )

    def _build_collaboration_prompt(
        self,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        peer_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """组装协作阶段使用的 Prompt。"""
        return self._prompt_builder.build_collaboration_prompt(
            spec=spec,
            loop_round=loop_round,
            context=context,
            peer_cards=peer_cards,
            assigned_command=assigned_command,
            work_log_context=self._work_log_context(limit=14),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
        )

    def _work_log_context(self, *, limit: int = 16) -> Dict[str, Any]:
        """裁剪工作日志，生成可放入 Prompt 的轻量上下文。"""
        return self._work_log_manager.build_context(str(self.session_id or ""), limit=limit)

    def _history_items_for_agent_prompt(
        self,
        *,
        agent_name: str,
        history_cards: List[AgentEvidence],
        dialogue_items: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        # compatibility shim: moved to context_builders.history_items_for_agent_prompt
        """整理单 Agent Prompt 需要看到的历史条目摘要。"""
        return history_items_for_agent_prompt_ctx(
            agent_name=agent_name,
            history_cards=history_cards,
            dialogue_items=dialogue_items,
            limit=limit,
        )

    def _peer_items_for_collaboration_prompt(
        self,
        *,
        spec_name: str,
        peer_cards: List[AgentEvidence],
        dialogue_items: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        # compatibility shim: moved to context_builders.peer_items_for_collaboration_prompt
        """整理协作 Prompt 需要的同伴结论条目。"""
        return peer_items_for_collaboration_prompt_ctx(
            spec_name=spec_name,
            peer_cards=peer_cards,
            dialogue_items=dialogue_items,
            limit=limit,
        )

    def _compact_round_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """压缩 round 级上下文，避免 Prompt 被无关历史撑大。"""
        incident_summary = context.get("incident_summary")
        if not isinstance(incident_summary, dict):
            incident_summary = {}
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
                "message": str(first.get("message") or "")[:320],
            }
        if "urls" in parsed_data and parsed_data.get("urls"):
            compact_parsed["urls"] = self._compact_value(parsed_data.get("urls"))
        if "class_names" in parsed_data and parsed_data.get("class_names"):
            compact_parsed["class_names"] = self._compact_value(parsed_data.get("class_names"))

        if not compact_parsed:
            for key, value in list(parsed_data.items())[:6]:
                if value not in (None, "", [], {}):
                    compact_parsed[str(key)] = self._compact_value(value)

        investigation_leads = context.get("investigation_leads")
        if not isinstance(investigation_leads, dict):
            investigation_leads = {}
        compact_leads = {
            "api_endpoints": self._normalize_text_items(investigation_leads.get("api_endpoints"), limit=20, width=220),
            "service_names": self._normalize_text_items(investigation_leads.get("service_names"), limit=20, width=160),
            "code_artifacts": self._normalize_text_items(investigation_leads.get("code_artifacts"), limit=24, width=240),
            "class_names": self._normalize_text_items(investigation_leads.get("class_names"), limit=24, width=180),
            "database_tables": self._normalize_database_tables(
                investigation_leads.get("database_tables") or interface_mapping.get("database_tables") or []
            ),
            "monitor_items": self._normalize_text_items(investigation_leads.get("monitor_items"), limit=20, width=180),
            "dependency_services": self._normalize_text_items(investigation_leads.get("dependency_services"), limit=20, width=160),
            "trace_ids": self._normalize_text_items(investigation_leads.get("trace_ids"), limit=12, width=160),
            "error_keywords": self._normalize_text_items(investigation_leads.get("error_keywords"), limit=20, width=160),
            "domain": str(investigation_leads.get("domain") or interface_mapping.get("domain") or "").strip(),
            "aggregate": str(investigation_leads.get("aggregate") or interface_mapping.get("aggregate") or "").strip(),
            "owner_team": str(investigation_leads.get("owner_team") or interface_mapping.get("owner_team") or "").strip(),
            "owner": str(investigation_leads.get("owner") or interface_mapping.get("owner") or "").strip(),
        }

        return {
            "incident_summary": {
                "title": str(incident_summary.get("title") or "")[:220],
                "description": str(incident_summary.get("description") or "")[:900],
                "severity": str(incident_summary.get("severity") or "")[:40],
                "service_name": str(incident_summary.get("service_name") or "")[:180],
            },
            "log_excerpt": str(context.get("log_excerpt") or "")[:2200],
            "parsed_data": compact_parsed,
            "execution_mode": str(context.get("execution_mode") or "")[:40],
            "available_analysis_agents": list(context.get("available_analysis_agents") or [])[:16],
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
                "database_tables": self._normalize_database_tables(interface_mapping.get("database_tables") or interface_mapping.get("db_tables") or []),
                "code_artifacts": self._normalize_text_items(interface_mapping.get("code_artifacts"), limit=12, width=240),
                "dependency_services": self._normalize_text_items(interface_mapping.get("dependency_services"), limit=20, width=160),
                "monitor_items": self._normalize_text_items(interface_mapping.get("monitor_items"), limit=20, width=180),
            },
            "investigation_leads": compact_leads,
            "asset_counts": {
                "runtime": int(context.get("runtime_assets_count") or 0),
                "development": int(context.get("dev_assets_count") or 0),
                "design": int(context.get("design_assets_count") or 0),
            },
        }

    async def _build_agent_context_with_tools(
        self,
        *,
        agent_name: str,
        compact_context: Dict[str, Any],
        loop_round: int,
        round_number: int,
        assigned_command: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        为指定 Agent 组装带工具结果的执行上下文。

        如果工具构建失败，这里不会直接打断整轮分析，而是发出审计事件后
        回退到纯上下文模式，让 Agent 仍可基于已有证据执行受限分析。
        """
        try:
            tool_context = await agent_tool_context_service.build_context(
                agent_name=agent_name,
                compact_context=compact_context,
                incident_context=self._input_context,
                assigned_command=assigned_command,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            await self._emit_event(
                {
                    "type": "agent_tool_context_failed",
                    "phase": "analysis",
                    "agent_name": agent_name,
                    "loop_round": loop_round,
                    "round_number": round_number,
                    "error": error_text,
                }
            )
            return compact_context

        tool_name = str(tool_context.get("name") or "").strip().lower()
        if tool_name in {"", "none"}:
            # 未配置外部工具的 Agent 直接沿用 compact_context，避免制造伪造的工具轨迹。
            return compact_context

        compact_tool_data = self._compact_value(tool_context.get("data") or {})
        detailed_tool_data = self._tool_event_value(tool_context.get("data") or {})
        command_gate = self._tool_event_value(tool_context.get("command_gate") or {})
        audit_log = self._tool_event_value(tool_context.get("audit_log") or [])
        focused_context = agent_tool_context_service.build_focused_context(
            agent_name=agent_name,
            compact_context=compact_context,
            incident_context=self._input_context,
            tool_context=tool_context,
            assigned_command=assigned_command,
        )
        focused_preview = self._compact_value(focused_context)
        focused_detail = self._tool_event_value(focused_context)
        await self._emit_event(
            {
                "type": "agent_tool_context_prepared",
                "phase": "analysis",
                "agent_name": agent_name,
                "loop_round": loop_round,
                "round_number": round_number,
                "tool_name": str(tool_context.get("name") or ""),
                "enabled": bool(tool_context.get("enabled")),
                "used": bool(tool_context.get("used")),
                "status": str(tool_context.get("status") or ""),
                "summary": str(tool_context.get("summary") or "")[:260],
                "data_preview": compact_tool_data,
                "data_detail": detailed_tool_data,
                "focused_preview": focused_preview,
                "focused_detail": focused_detail,
                "command_gate": command_gate,
                "audit_log": audit_log,
                "execution_path": str(tool_context.get("execution_path") or ""),
                "permission_decision": self._tool_event_value(tool_context.get("permission_decision") or {}),
            }
        )
        logger.info(
            "agent_tool_context_prepared",
            session_id=self.session_id,
            agent_name=agent_name,
            loop_round=loop_round,
            round_number=round_number,
            tool_name=str(tool_context.get("name") or ""),
            enabled=bool(tool_context.get("enabled")),
            used=bool(tool_context.get("used")),
            status=str(tool_context.get("status") or ""),
            summary=str(tool_context.get("summary") or "")[:260],
            data_preview=compact_tool_data,
            focused_preview=focused_preview,
            command_gate=command_gate,
            audit_log=audit_log,
            execution_path=str(tool_context.get("execution_path") or ""),
            permission_decision=self._tool_event_value(tool_context.get("permission_decision") or {}),
        )
        if isinstance(audit_log, list):
            for idx, record in enumerate(audit_log, start=1):
                if not isinstance(record, dict):
                    continue
                logger.info(
                    "agent_tool_audit",
                    session_id=self.session_id,
                    agent_name=agent_name,
                    loop_round=loop_round,
                    round_number=round_number,
                    audit_index=idx,
                    audit_record=record,
                )
                await self._emit_event(
                    {
                        "type": "agent_tool_io",
                        "phase": "analysis",
                        "agent_name": agent_name,
                        "loop_round": loop_round,
                        "round_number": round_number,
                        "tool_name": str(tool_context.get("name") or ""),
                        "io_action": str(record.get("action") or ""),
                        "io_status": str(record.get("status") or ""),
                        "io_call_id": str(record.get("call_id") or ""),
                        "io_timestamp": str(record.get("timestamp") or ""),
                        "io_duration_ms": record.get("duration_ms"),
                        "io_request_summary": str(record.get("request_summary") or ""),
                        "io_response_summary": str(record.get("response_summary") or ""),
                        "io_detail": self._tool_event_value(record.get("detail") or {}),
                    }
                )

        return {
            **compact_context,
            "focused_context": focused_detail,
            "tool_context": {
                "name": tool_context.get("name"),
                "enabled": bool(tool_context.get("enabled")),
                "used": bool(tool_context.get("used")),
                "status": str(tool_context.get("status") or ""),
                "summary": str(tool_context.get("summary") or "")[:320],
                "data": compact_tool_data,
                "command_gate": command_gate,
                "audit_log": audit_log,
            },
        }

    def _apply_tool_switch_to_spec(
        self,
        *,
        spec: AgentSpec,
        context_with_tools: Dict[str, Any],
    ) -> AgentSpec:
        """根据工具状态裁剪 AgentSpec，避免把失效工具继续暴露给模型。"""
        tool_ctx = context_with_tools.get("tool_context")
        if not isinstance(tool_ctx, dict):
            return spec
        status = str(tool_ctx.get("status") or "").strip().lower()
        enabled = bool(tool_ctx.get("enabled"))
        used = bool(tool_ctx.get("used"))
        if enabled and used and status == "ok":
            return spec
        if spec.name in {
            "ProblemAnalysisAgent",
            "LogAgent",
            "DomainAgent",
            "CodeAgent",
            "DatabaseAgent",
            "MetricsAgent",
            "ChangeAgent",
            "RunbookAgent",
            "RuleSuggestionAgent",
            "CriticAgent",
            "RebuttalAgent",
            "JudgeAgent",
            "VerificationAgent",
        } and tuple(spec.tools or ()):
            return replace(spec, tools=())
        return spec

    def _compact_value(self, value: Any) -> Any:
        """压缩任意值，控制上下文和事件体积。"""
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

    def _tool_event_value(self, value: Any, depth: int = 0) -> Any:
        """把工具执行结果压缩成适合审计事件持久化的值。"""
        if depth >= 4:
            return "..."
        if isinstance(value, str):
            return truncate_text_with_ref(
                value,
                max_chars=1600,
                session_id=str(self.session_id or ""),
                category="tool_event_value",
                metadata={"depth": depth},
            )
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [self._tool_event_value(item, depth + 1) for item in value[:20]]
        if isinstance(value, dict):
            return {
                str(key): self._tool_event_value(item, depth + 1)
                for key, item in list(value.items())[:30]
            }
        return str(value)[:600]

    def _to_compact_json(self, value: Any) -> str:
        """把对象序列化成紧凑 JSON，便于日志落盘。"""
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return "{}"

    def _agent_max_tokens(self, agent_name: str) -> int:
        """按 Agent 角色返回本轮允许使用的最大 token 预算。"""
        if agent_name == "JudgeAgent":
            configured = int(settings.DEBATE_JUDGE_MAX_TOKENS)
            return max(900, min(configured, 1600))
        if agent_name in {"CriticAgent", "RebuttalAgent"}:
            configured = int(settings.DEBATE_REVIEW_MAX_TOKENS)
            return max(560, min(configured, 1100))
        if agent_name == "ProblemAnalysisAgent":
            configured = int(settings.DEBATE_ANALYSIS_MAX_TOKENS)
            if self._deployment_profile_name in {"investigation_full", "production_governed"} and not self.turns:
                return max(280, min(configured, 360))
            if not self._require_verification_plan and not self.turns:
                return max(360, min(configured, 480))
            return max(620, min(configured, 1100))
        configured = int(settings.DEBATE_ANALYSIS_MAX_TOKENS)
        return max(560, min(configured, 1100))

    def _agent_timeout_plan(self, agent_name: str) -> List[float]:
        """按 Agent 角色生成 HTTP 超时与重试超时计划。"""
        if agent_name == "JudgeAgent":
            if not self._require_verification_plan:
                first_timeout = float(max(40, int(settings.llm_judge_timeout)))
                retry_timeout = float(max(first_timeout + 10, int(settings.llm_judge_retry_timeout) + 15))
                return [first_timeout, retry_timeout]
            first_timeout = float(max(18, int(settings.llm_judge_timeout)))
            retry_timeout = float(max(first_timeout, int(settings.llm_judge_retry_timeout)))
            return [first_timeout, retry_timeout]
        if agent_name == "ProblemAnalysisAgent":
            if not self._require_verification_plan:
                return [float(max(45, int(settings.llm_analysis_timeout)))]
            first_timeout = float(max(12, int(settings.llm_analysis_timeout)))
            retry_timeout = float(max(first_timeout, min(int(settings.llm_analysis_timeout) + 10, 60)))
            return [first_timeout, retry_timeout]
        if agent_name in {"CriticAgent", "RebuttalAgent"}:
            return [float(max(12, int(settings.llm_review_timeout)))]
        return [float(max(12, int(settings.llm_analysis_timeout)))]

    def _agent_http_timeout(self, agent_name: str) -> int:
        """返回单次 LLM HTTP 请求允许的最长超时时间。"""
        if agent_name == "JudgeAgent":
            if not self._require_verification_plan:
                return max(45, min(int(settings.llm_judge_retry_timeout) + 20, 120))
            return max(20, min(int(settings.llm_judge_retry_timeout), 120))
        if agent_name in {"CriticAgent", "RebuttalAgent"}:
            return max(15, min(int(settings.llm_review_timeout), 90))
        return max(15, min(int(settings.llm_analysis_timeout), 90))

    def _agent_queue_timeout(self, agent_name: str) -> float:
        """返回该 Agent 在 LLM 队列里允许等待的最长时间。"""
        base_timeout = float(max(2, int(settings.llm_queue_timeout)))
        analysis_timeout = float(max(base_timeout, int(settings.llm_analysis_queue_timeout)))
        metrics_timeout = float(max(analysis_timeout, int(settings.llm_metrics_queue_timeout)))
        judge_timeout = float(max(analysis_timeout, int(settings.llm_judge_queue_timeout)))
        if agent_name == "JudgeAgent":
            return judge_timeout
        if agent_name == "ProblemAnalysisAgent":
            if self._deployment_profile_name in {"investigation_full", "production_governed"} and not self.turns:
                return float(max(min(judge_timeout - 5.0, judge_timeout), analysis_timeout + 10.0, 55.0))
            return float(max(min(judge_timeout - 10.0, judge_timeout), analysis_timeout + 5.0, 50.0))
        if agent_name == "MetricsAgent":
            if self._deployment_profile_name in {"investigation_full", "production_governed"}:
                return float(max(metrics_timeout, 75.0))
            return float(max(metrics_timeout, 60.0))
        if (
            self._deployment_profile_name in {"investigation_full", "production_governed"}
            and agent_name in {"LogAgent", "CodeAgent", "DatabaseAgent", "ChangeAgent", "DomainAgent"}
        ):
            return float(max(analysis_timeout, 45.0))
        if agent_name in {"CriticAgent", "RebuttalAgent", "VerificationAgent"}:
            return float(max(base_timeout + 10.0, 40.0))
        return base_timeout

    def _remaining_session_budget_seconds(self) -> Optional[float]:
        """计算当前会话剩余的总预算秒数。"""
        if self._session_deadline_monotonic is None:
            return None
        return max(0.0, self._session_deadline_monotonic - monotonic())

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
        """在超时重试前压缩 Prompt，减少无效上下文。"""
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
        """把普通 Agent 原始输出解析成统一结构。"""
        return normalize_agent_output_parser(
            agent_name,
            raw_content,
            judge_fallback_summary=self.JUDGE_FALLBACK_SUMMARY,
        )

    def _normalize_commander_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        """把主 Agent 原始输出解析成统一结构。"""
        return normalize_commander_output_parser(parsed, raw_content)

    def _normalize_normal_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        """把普通结构化输出解析成统一格式。"""
        return normalize_normal_output(parsed, raw_content)

    def _normalize_judge_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        """把 Judge 输出解析成最终裁决格式。"""
        return normalize_judge_output(
            parsed,
            raw_content,
            fallback_summary=self.JUDGE_FALLBACK_SUMMARY,
        )

    def _is_placeholder_summary(self, summary: str) -> bool:
        """判断摘要是否仍处于占位态，不能作为最终结论。"""
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
        """在缺少 Judge 结果时，从历史卡片合成一个谨慎的最终结论。"""
        candidates: List[AgentEvidence] = []
        for card in history_cards:
            if card.agent_name == "JudgeAgent":
                continue
            if self._is_degraded_output(card.raw_output if isinstance(card.raw_output, dict) else {}):
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
            "DatabaseAgent": "database_signal",
            "LogAgent": "runtime_log",
            "DomainAgent": "domain_mapping",
            "MetricsAgent": "metrics_signal",
            "ChangeAgent": "change_correlation",
            "RunbookAgent": "runbook_reference",
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

        best_summary = extract_readable_text(
            best.summary or best.conclusion,
            fallback=str(best.summary or best.conclusion),
            max_len=260,
        )
        best_conclusion = extract_readable_text(
            best.conclusion or best.summary,
            fallback=str(best.conclusion or best.summary),
            max_len=260,
        )
        key_factors = [f"{best.agent_name}: {best_summary[:140]}"]
        if second:
            second_summary = extract_readable_text(
                second.summary or second.conclusion,
                fallback=str(second.summary or second.conclusion),
                max_len=260,
            )
            key_factors.append(f"{second.agent_name}: {second_summary[:140]}")

        return {
            "confidence": root_confidence,
            "final_judgment": {
                "root_cause": {
                    "summary": best_conclusion[:260],
                    "category": category,
                    "confidence": root_confidence,
                },
                "evidence_chain": evidence_chain,
                "fix_recommendation": {
                    "summary": best_conclusion[:260],
                    "steps": [best_summary[:180]],
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
                    "risk_factors": ["JudgeAgent 未返回有效裁决，系统采用专家结论保守收口"],
                    "mitigation_suggestions": ["补充关键指标后可再次触发全量辩论"],
                },
            },
            "decision_rationale": {
                "key_factors": key_factors,
                "reasoning": "JudgeAgent 未在时限内返回，系统已基于成功 Agent 的高置信结论自动收敛。",
            },
            "action_items": [
                {"priority": 1, "action": best_conclusion[:180], "owner": "待确认"},
            ],
            "responsible_team": {"team": "待确认", "owner": "待确认"},
        }

    def _build_final_payload(
        self,
        history_cards: List[AgentEvidence],
        consensus_reached: bool,
        executed_rounds: int,
    ) -> Dict[str, Any]:
        """
        汇总本次会话的最终对外输出。

        优先采用 `JudgeAgent` 的结构化裁决；若 Judge 缺席，则退回到基于
        历史卡片的保守合成逻辑，确保前端和报告端始终能拿到完整结果对象。
        """
        judge_turn = next((turn for turn in reversed(self.turns) if turn.agent_name == "JudgeAgent"), None)
        verification_turn = next(
            (turn for turn in reversed(self.turns) if turn.agent_name == "VerificationAgent"),
            None,
        )

        # 第一优先级始终是 Judge 的结构化输出；只有它缺席或输出占位内容时，
        # 才退回到基于历史卡片的保守合成逻辑。
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

        verification_plan = []
        if verification_turn and isinstance(verification_turn.output_content, dict):
            raw_plan = verification_turn.output_content.get("verification_plan")
            if isinstance(raw_plan, list):
                verification_plan = [item for item in raw_plan if isinstance(item, dict)]
        # VerificationAgent 的结果只补充验证计划，不覆盖最终根因裁决。
        if isinstance(final_judgment, dict):
            if verification_plan:
                final_judgment["verification_plan"] = verification_plan
            elif isinstance(final_judgment.get("verification_plan"), list):
                verification_plan = [item for item in final_judgment.get("verification_plan") if isinstance(item, dict)]

        root_cause = final_judgment.get("root_cause") if isinstance(final_judgment, dict) else {}
        root_summary = ""
        if isinstance(root_cause, dict):
            root_summary = str(root_cause.get("summary") or "").strip()
        if self._is_placeholder_summary(root_summary):
            # 如果 Judge 只返回了占位语句，就从历史专家输出里再做一次保守合成，
            # 保证最终结果至少落在“低置信但可解释”的级别，而不是空白。
            synthesized = self._synthesize_final_from_history(history_cards)
            if synthesized:
                confidence = float(synthesized.get("confidence") or confidence or 0.0)
                final_judgment = synthesized.get("final_judgment") or final_judgment
                decision_rationale = synthesized.get("decision_rationale") or decision_rationale
                action_items = synthesized.get("action_items") or action_items
                responsible_team = synthesized.get("responsible_team") or responsible_team

        coverage = self._count_key_evidence_coverage(history_cards)
        if coverage["degraded"] + coverage["missing"] >= 2:
            confidence = min(float(confidence or 0.0), 0.45)
            if not isinstance(final_judgment, dict):
                final_judgment = {}
            risk_assessment = final_judgment.get("risk_assessment")
            if not isinstance(risk_assessment, dict):
                risk_assessment = {}
            factors = [
                str(item).strip()
                for item in list(risk_assessment.get("risk_factors") or [])
                if str(item).strip()
            ]
            factors.append(
                f"关键证据不足：成功={coverage['ok']}，降级={coverage['degraded']}，缺失={coverage['missing']}"
            )
            risk_assessment["risk_factors"] = list(dict.fromkeys(factors))[:6]
            risk_assessment["risk_level"] = "high"
            final_judgment["risk_assessment"] = risk_assessment
            if not isinstance(decision_rationale, dict):
                decision_rationale = {}
            reasoning = str(decision_rationale.get("reasoning") or "").strip()
            suffix = "关键证据 Agent 覆盖不足，本轮结论仅作为低置信方向判断。"
            decision_rationale["reasoning"] = f"{reasoning} {suffix}".strip()
            if not isinstance(action_items, list):
                action_items = []
            action_items = [
                {
                    "priority": 1,
                    "action": "优先恢复失败/缺失的关键证据 Agent（Log/Code/Database/Metrics）并重跑分析",
                    "owner": "待确认",
                },
                *[item for item in action_items if isinstance(item, dict)],
            ][:3]

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
            "verification_plan": verification_plan,
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
        """标准化 LLM Base URL，统一补齐版本后缀。"""
        base = settings.LLM_BASE_URL.rstrip("/")
        if base.endswith("/v1") or base.endswith("/v3"):
            return base
        return f"{base}/v3"

    def _chat_endpoint(self) -> str:
        """返回当前运行时实际访问的 chat completions 端点。"""
        base = self._base_url_for_llm()
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    async def _emit_event(self, event: Dict[str, Any]) -> None:
        """执行发射事件，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._event_dispatcher.bind(
            trace_id=self.trace_id,
            session_id=str(self.session_id or ""),
            callback=self._event_callback,
        )
        await self._event_dispatcher.emit(event)


langgraph_runtime_orchestrator = LangGraphRuntimeOrchestrator(
    consensus_threshold=settings.DEBATE_CONSENSUS_THRESHOLD,
    max_rounds=settings.DEBATE_MAX_ROUNDS,
)
