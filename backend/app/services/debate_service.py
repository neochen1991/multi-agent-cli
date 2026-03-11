"""
辩论服务模块

本模块是辩论流程的核心服务层，负责：
1. 辩论会话的生命周期管理（创建、执行、取消、查询）
2. 状态转换控制（PENDING -> RUNNING -> COMPLETED 等）
3. 事件流处理和实时推送
4. 错误分类和恢复策略

主要组件：
- DebateService: 辩论服务主类
- 状态转换机: _STATUS_TRANSITIONS 定义合法的状态转换
- 错误分类器: _classify_error 用于错误诊断

Debate Service

整合资产采集、AI辩论分析和报告生成三个核心模块。
"""

import asyncio
import re
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import structlog

from app.models.debate import (
    DebateSession,
    DebateRound,
    DebateResult,
    DebateStatus,
    DebatePhase,
    EvidenceItem,
    FixRecommendation,
    ImpactAnalysis,
    RiskAssessment,
    RootCauseCandidate,
)
from app.models.incident import Incident
from app.flows.debate_flow import (
    create_ai_debate_orchestrator,
    normalize_analysis_depth_mode,
    resolve_analysis_depth_max_rounds,
)
from app.flows.context import context_manager
from app.services.asset_collection_service import asset_collection_service
from app.services.asset_service import asset_service
from app.services.report_generation_service import report_generation_service
from app.config import settings
from app.core.event_schema import enrich_event, new_trace_id
from app.core.observability import metrics_store
from app.runtime.evidence import normalize_evidence_items
from app.runtime.langgraph.parsers import extract_readable_text
from app.runtime.judgement import causal_score, has_cross_source_evidence, score_topology_propagation
from app.runtime.langgraph.deployment_center import deployment_center
from app.runtime.langgraph.services.review_boundary import ReviewBoundary
from app.runtime_serve import normalize_execution_mode
from app.runtime.langgraph.strategy_center import runtime_strategy_center
from app.repositories.debate_repository import (
    DebateRepository,
    InMemoryDebateRepository,
    FileDebateRepository,
)

logger = structlog.get_logger()
review_boundary = ReviewBoundary()


class HumanReviewRequired(RuntimeError):
    """表示当前分析必须暂停，等待人工审核后才能继续推进。"""

    def __init__(self, session_id: str, reason: str, review_payload: Optional[Dict[str, Any]] = None, resume_from_step: str = ""):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self.session_id = session_id
        self.reason = str(reason or "")
        self.review_payload = dict(review_payload or {})
        self.resume_from_step = str(resume_from_step or "")
        super().__init__(self.reason or "human review required")


class DebateService:
    """
    辩论服务 - 核心业务逻辑

    整合三大核心模块：
    1. 资产采集：收集日志、指标、代码等分析素材
    2. AI 辩论：多 Agent 协作分析根因
    3. 报告生成：输出结构化的分析报告

    状态机设计：
    - PENDING: 待执行
    - RUNNING: 运行中
    - ANALYZING: 分析阶段
    - DEBATING: 辩论阶段
    - JUDGING: 裁决阶段
    - WAITING: 等待中
    - RETRYING: 重试中
    - COMPLETED: 已完成
    - FAILED: 失败
    - CANCELLED: 已取消
    - CRITIQUING: 质疑阶段
    - REBUTTING: 反驳阶段
    """

    # 状态转换规则：定义每个状态可以转换到的合法目标状态
    # 例如：PENDING 状态只能转换到 RUNNING、CANCELLED 或 FAILED
    _STATUS_TRANSITIONS: Dict[DebateStatus, set[DebateStatus]] = {
        # 待执行 -> 运行中、已取消、失败
        DebateStatus.PENDING: {DebateStatus.RUNNING, DebateStatus.CANCELLED, DebateStatus.FAILED},
        # 运行中 -> 分析中、辩论中、裁决中、等待、重试、取消、失败、完成
        DebateStatus.RUNNING: {
            DebateStatus.ANALYZING,
            DebateStatus.DEBATING,
            DebateStatus.JUDGING,
            DebateStatus.WAITING,
            DebateStatus.RETRYING,
            DebateStatus.CANCELLED,
            DebateStatus.FAILED,
            DebateStatus.COMPLETED,
        },
        # 分析中 -> 运行中、辩论中、等待、重试、取消、失败
        DebateStatus.ANALYZING: {
            DebateStatus.RUNNING,
            DebateStatus.DEBATING,
            DebateStatus.WAITING,
            DebateStatus.RETRYING,
            DebateStatus.CANCELLED,
            DebateStatus.FAILED,
        },
        # 辩论中 -> 运行中、裁决中、等待、重试、取消、失败
        DebateStatus.DEBATING: {
            DebateStatus.RUNNING,
            DebateStatus.JUDGING,
            DebateStatus.WAITING,
            DebateStatus.RETRYING,
            DebateStatus.CANCELLED,
            DebateStatus.FAILED,
        },
        # 裁决中 -> 完成、等待、重试、取消、失败
        DebateStatus.JUDGING: {
            DebateStatus.COMPLETED,
            DebateStatus.WAITING,
            DebateStatus.RETRYING,
            DebateStatus.CANCELLED,
            DebateStatus.FAILED,
        },
        # 等待 -> 运行中、分析中、辩论中、重试、取消、失败
        DebateStatus.WAITING: {DebateStatus.RUNNING, DebateStatus.ANALYZING, DebateStatus.DEBATING, DebateStatus.RETRYING, DebateStatus.CANCELLED, DebateStatus.FAILED},
        # 重试 -> 运行中、分析中、辩论中、裁决中、等待、取消、失败
        DebateStatus.RETRYING: {DebateStatus.RUNNING, DebateStatus.ANALYZING, DebateStatus.DEBATING, DebateStatus.JUDGING, DebateStatus.WAITING, DebateStatus.CANCELLED, DebateStatus.FAILED},
        # 失败 -> 重试、取消
        DebateStatus.FAILED: {DebateStatus.RETRYING, DebateStatus.CANCELLED},
        # 已取消 -> 重试
        DebateStatus.CANCELLED: {DebateStatus.RETRYING},
        # 已完成 -> 终态，不可转换
        DebateStatus.COMPLETED: set(),
        # 质疑中 -> 反驳中、裁决中、失败
        DebateStatus.CRITIQUING: {DebateStatus.REBUTTING, DebateStatus.JUDGING, DebateStatus.FAILED},
        # 反驳中 -> 裁决中、失败
        DebateStatus.REBUTTING: {DebateStatus.JUDGING, DebateStatus.FAILED},
    }

    def __init__(self, repository: Optional[DebateRepository] = None):
        """
        初始化辩论服务

        Args:
            repository: 辩论数据存储库，如果未提供则根据配置选择文件或内存存储
        """
        self._repository = repository or (
            FileDebateRepository()
            if settings.LOCAL_STORE_BACKEND == "file"
            else InMemoryDebateRepository()
        )

    @staticmethod
    def _next_event_sequence(session: DebateSession) -> int:
        """
        获取下一个事件序号

        用于事件排序和幂等性保证。

        Args:
            session: 辩论会话

        Returns:
            int: 下一个事件序号
        """
        current = int((session.context or {}).get("_event_sequence") or 0)
        next_value = current + 1
        session.context["_event_sequence"] = next_value
        return next_value

    @staticmethod
    def _classify_error(error_text: str) -> Dict[str, Any]:
        """
        分类错误信息

        根据错误文本判断错误类型、是否可恢复以及重试建议。

        Args:
            error_text: 错误信息文本

        Returns:
            Dict[str, Any]: 包含 error_code、error_message、recoverable、retry_hint 的字典
        """
        text = str(error_text or "").strip()
        lowered = text.lower()
        reset_match = re.search(r"reset at ([0-9:\-+\sA-Z]+)", text, flags=re.IGNORECASE)
        reset_at = str(reset_match.group(1) or "").strip() if reset_match else ""
        # 限流错误优先级高于“无有效结论”，因为上层 often 会把底层 429 包进结论错误里。
        if "rate_limit" in lowered or "429" in lowered or "accountquotaexceeded" in lowered or "toomanyrequests" in lowered:
            retry_hint = "稍后重试，或降低并发配置"
            if reset_at:
                retry_hint = f"模型额度已耗尽，请在 {reset_at} 后重试，或降低并发配置"
            return {
                "error_code": "LLM_RATE_LIMITED",
                "error_message": text,
                "recoverable": True,
                "retry_hint": retry_hint,
            }
        # 未获得有效大模型结论
        if "未获得有效大模型结论" in text:
            return {
                "error_code": "NO_EFFECTIVE_LLM_CONCLUSION",
                "error_message": text,
                "recoverable": True,
                "retry_hint": "补充更完整的日志、堆栈和监控现象后重试分析",
            }
        # 超时错误
        if "timeout" in lowered or "超时" in text:
            return {
                "error_code": "AGENT_TIMEOUT",
                "error_message": text,
                "recoverable": True,
                "retry_hint": "可先降低辩论轮次或缩短输入日志后重试",
            }
        # 内部运行时错误
        return {
            "error_code": "INTERNAL_RUNTIME_ERROR",
            "error_message": text or "unknown error",
            "recoverable": False,
            "retry_hint": "请查看后端日志定位异常后重试",
        }

    @staticmethod
    def _should_degrade_missing_effective_conclusion(error_text: str) -> bool:
        """判断“无有效结论”是否由超时/限流等可恢复故障触发，应降级产出结果而非直接失败。"""
        text = str(error_text or "").strip()
        lowered = text.lower()
        if "未获得有效大模型结论" not in text:
            return False
        timeout_markers = (
            "timeout",
            "timed out",
            "session timeout",
            "llm queue timeout",
            "llm invoke timeout",
        )
        rate_limit_markers = (
            "llm_rate_limited",
            "429",
            "rate limit",
            "accountquotaexceeded",
            "toomanyrequests",
            "serveroverloaded",
        )
        return any(marker in lowered for marker in (*timeout_markers, *rate_limit_markers))
    
    async def create_session(
        self,
        incident: Incident,
        max_rounds: Optional[int] = None,
        execution_mode: str = "standard",
        analysis_depth_mode: Optional[str] = None,
        deployment_profile: str = "",
    ) -> DebateSession:
        """
        创建辩论会话

        根据故障事件创建新的辩论会话，包括：
        1. 生成会话 ID
        2. 根据执行模式和严重程度选择运行策略
        3. 构建会话上下文
        4. 持久化会话

        Args:
            incident: 关联的故障事件
            max_rounds: 最大辩论轮次（可选，1-8）
            execution_mode: 执行模式（standard/quick/background）

        Returns:
            DebateSession: 创建的辩论会话
        """
        # 生成唯一会话 ID
        session_id = f"deb_{uuid.uuid4().hex[:8]}"

        # 根据执行模式和严重程度选择运行策略
        debate_config: Dict[str, Any] = {}
        normalized_mode = normalize_execution_mode(execution_mode).value
        severity_text = str(getattr(incident.severity, "value", incident.severity) or "")
        selected_strategy = runtime_strategy_center.select(
            severity=severity_text,
            execution_mode=normalized_mode,
        )
        selected_deployment = deployment_center.select(
            severity=severity_text,
            execution_mode=normalized_mode,
            requested_profile=deployment_profile,
        )
        # quick 执行模式始终强制走最浅分析深度，其他模式则沿用用户或设置页传入的深度偏好。
        requested_depth_mode = normalize_analysis_depth_mode(analysis_depth_mode)
        effective_depth_mode = "quick" if normalized_mode == "quick" else requested_depth_mode
        debate_config["analysis_depth_mode"] = effective_depth_mode
        debate_config["max_rounds"] = resolve_analysis_depth_max_rounds(max_rounds, effective_depth_mode)

        # 构建会话上下文
        session_context: Dict[str, Any] = {
            "incident": incident.model_dump(),
            "log_content": incident.log_content,
            "exception_stack": incident.exception_stack,
            "parsed_data": incident.parsed_data,
            "_event_sequence": 0,  # 事件序号计数器
            # 中文注释：execution_mode 表示用户选择的分析策略模式，不再被后台投递方式覆盖。
            "execution_mode": normalized_mode,
            "requested_execution_mode": normalized_mode,
            # 中文注释：execution_delivery_mode 单独表示当前任务是前台直执还是后台投递。
            "execution_delivery_mode": "foreground",
            "analysis_depth_mode": effective_depth_mode,
            "runtime_strategy": selected_strategy,
            "deployment_profile": selected_deployment,
        }
        if debate_config:
            session_context["debate_config"] = debate_config
        # 快速模式强制单轮
        if normalized_mode == "quick":
            cfg = dict(session_context.get("debate_config") or {})
            cfg["max_rounds"] = 1
            session_context["debate_config"] = cfg

        # 创建会话对象
        session = DebateSession(
            id=session_id,
            incident_id=incident.id,
            status=DebateStatus.PENDING,
            context=session_context,
        )

        # 持久化会话
        await self._repository.save_session(session)

        logger.info(
            "debate_session_created",
            session_id=session_id,
            incident_id=incident.id,
            max_rounds=debate_config.get("max_rounds"),
            analysis_depth_mode=effective_depth_mode,
            execution_mode=normalized_mode,
            runtime_strategy=str(selected_strategy.get("name") or ""),
            deployment_profile=str(selected_deployment.get("name") or ""),
        )
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        """
        获取辩论会话

        Args:
            session_id: 会话 ID

        Returns:
            Optional[DebateSession]: 会话对象，如果不存在则返回 None
        """
        return await self._repository.get_session(session_id)

    async def update_session(self, session: DebateSession) -> DebateSession:
        """
        更新会话状态

        Args:
            session: 要更新的会话对象

        Returns:
            DebateSession: 更新后的会话
        """
        return await self._repository.save_session(session)

    async def execute_debate(
        self,
        session_id: str,
        event_callback=None,
        retry_failed_only: bool = False,
    ) -> DebateResult:
        """
        执行完整的辩论流程

        这是辩论服务的核心方法，整合三大模块：
        1. 资产采集：收集日志、代码、配置等分析素材
        2. AI 辩论分析：多 Agent 协作进行根因分析
        3. 报告生成：输出结构化的分析报告

        执行流程：
        1. 检查会话状态，确保可以执行
        2. 更新状态为 RUNNING -> ANALYZING
        3. 初始化会话上下文
        4. 发射初始种子证据事件
        5. 执行资产采集
        6. 执行 AI 辩论
        7. 生成报告
        8. 更新状态为 COMPLETED

        Args:
            session_id: 会话 ID
            event_callback: 事件回调函数，用于实时推送事件
            retry_failed_only: 是否仅重试失败部分

        Returns:
            DebateResult: 辩论结果

        Raises:
            ValueError: 会话不存在
            RuntimeError: 会话已取消
        """
        # 这段方法同时编排三条链路：资产采集、LangGraph 分析、报告生成。
        # 为了保证前端可回放和可恢复，所有关键状态变化都会被事件化并落盘。
        execute_started_at = datetime.utcnow()
        had_retry = False
        timeout_failure = False
        invalid_conclusion_failure = False

        # 先做会话状态门禁，避免对已完成、已取消或待人工审核会话重复执行。
        session = await self._repository.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        # 已完成的会话直接返回结果
        if session.status == DebateStatus.COMPLETED:
            existed = await self._repository.get_result(session_id)
            if existed:
                return existed
        # 已取消的会话抛出异常
        if session.status == DebateStatus.CANCELLED:
            raise RuntimeError(f"Session {session_id} is cancelled")

        human_review = self._get_human_review_state(session)
        pending_review_checkpoint = session.context.get("pending_review_checkpoint")
        if session.status == DebateStatus.WAITING and str(human_review.get("status") or "") == "pending":
            raise HumanReviewRequired(
                session_id=session_id,
                reason=str(human_review.get("reason") or "等待人工审核"),
                review_payload=dict(human_review.get("payload") or {}),
                resume_from_step=str(human_review.get("resume_from_step") or ""),
            )

        # trace_id 是整个分析链路的审计主键，后续事件、lineage、报告都依赖它串起来。
        trace_id = str(session.context.get("trace_id") or "").strip() or new_trace_id("deb")
        session.context["trace_id"] = trace_id
        session.context["is_cancel_requested"] = False
        session.context["retry_failed_only"] = bool(retry_failed_only)

        # 初始化会话上下文管理器
        await context_manager.init_session_context(session_id, session.context)
        event_log = session.context.get("event_log")
        if not isinstance(event_log, list):
            event_log = []

        async def _emit_and_record(event: Dict[str, Any]) -> None:
            """
            发射并记录事件

            将事件持久化到会话上下文，同时调用回调函数推送。

            Args:
                event: 事件数据
            """
            sequence = self._next_event_sequence(session)
            outbound = dict(event or {})
            outbound.setdefault("event_sequence", sequence)
            outbound.setdefault("session_id", session_id)
            payload = enrich_event(outbound, trace_id=trace_id)
            # 事件日志既服务前端实时展示，也服务历史页和断点恢复。
            event_log.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "event": payload,
                }
            )
            # 限制事件日志大小
            if len(event_log) > 500:
                del event_log[:-500]
            # 持续落库事件，保证分析中会话在刷新/历史页也可查看过程记录
            session.context["event_log"] = event_log
            session.updated_at = datetime.utcnow()
            await self._repository.save_session(session)
            await self._emit_event(event_callback, payload)

        resume_after_review = (
            session.status == DebateStatus.WAITING
            and str(human_review.get("status") or "") == "approved"
            and isinstance(pending_review_checkpoint, dict)
        )

        await self._transition_status(
            session,
            DebateStatus.RUNNING,
            event_callback=event_callback,
            phase="running",
            trace_id=trace_id,
        )
        if resume_after_review:
            await self._transition_status(
                session,
                DebateStatus.JUDGING,
                event_callback=event_callback,
                phase=DebatePhase.JUDGMENT.value,
                trace_id=trace_id,
            )
        else:
            await self._transition_status(
                session,
                DebateStatus.ANALYZING,
                event_callback=event_callback,
                phase=DebatePhase.ANALYSIS.value,
                trace_id=trace_id,
            )

        if resume_after_review:
            await _emit_and_record(
                {
                    "type": "human_review_resume_requested",
                    "session_id": session_id,
                    "status": session.status.value,
                    "phase": DebatePhase.JUDGMENT.value,
                    "resume_from_step": str(human_review.get("resume_from_step") or "report_generation"),
                }
            )
        else:
            # 发射会话开始事件
            await _emit_and_record(
                {
                    "type": "session_started",
                    "session_id": session_id,
                    "status": session.status.value,
                    "phase": DebatePhase.ANALYSIS.value,
                    "retry_failed_only": bool(retry_failed_only),
                }
            )
            # 发射种子证据事件（初始输入）
            await self._emit_seed_evidence_event(
                session=session,
                session_id=session_id,
                emit=_emit_and_record,
            )
        
        try:
            debate_result: Dict[str, Any] = {}
            if resume_after_review:
                checkpoint = dict(pending_review_checkpoint or {})
                assets = dict(checkpoint.get("assets") or {})
                debate_result = dict(checkpoint.get("debate_result") or {})
                session.current_phase = DebatePhase.JUDGMENT
            else:
                # ========== 模块1: 资产采集 ==========
                logger.info("asset_collection_started", session_id=session_id)
                session.current_phase = DebatePhase.ANALYSIS
                await _emit_and_record(
                    {
                        "type": "phase_changed",
                        "phase": session.current_phase.value,
                        "status": session.status.value,
                    }
                )

                assets = await self._collect_assets(
                    session.context,
                    event_callback=_emit_and_record,
                )
                session.context["assets"] = assets
                session.context["interface_mapping"] = dict(assets.get("interface_mapping") or {})
                session.context["investigation_leads"] = dict(assets.get("investigation_leads") or {})
                session.updated_at = datetime.utcnow()
                await self._repository.save_session(session)
                await context_manager.build_debate_context(
                    session_id=session_id,
                    base_context=session.context,
                    assets=assets,
                )

                logger.info(
                    "asset_collection_completed",
                    session_id=session_id,
                    runtime_count=len(assets.get("runtime_assets", [])),
                    dev_count=len(assets.get("dev_assets", [])),
                    design_count=len(assets.get("design_assets", []))
                )

                # ========== 模块2: AI辩论分析 ==========
                logger.info("ai_debate_started", session_id=session_id)
                await self._transition_status(
                    session,
                    DebateStatus.DEBATING,
                    event_callback=_emit_and_record,
                    phase="debating",
                    trace_id=trace_id,
                )
                await _emit_and_record(
                    {
                        "type": "phase_changed",
                        "phase": "debating",
                        "status": session.status.value,
                    }
                )

                execution_mode = str(session.context.get("execution_mode") or "standard").strip().lower()
                runtime_strategy = session.context.get("runtime_strategy")
                phase_mode = ""
                if isinstance(runtime_strategy, dict):
                    phase_mode = str(runtime_strategy.get("phase_mode") or "").strip().lower()
                max_attempts = 2
                allow_peer_fallback_judgment = False
                if execution_mode in {"quick", "background", "async"} or phase_mode in {
                    "economy",
                    "fast_track",
                    "failfast",
                }:
                    max_attempts = 1
                    allow_peer_fallback_judgment = True
                attempt = 0
                while attempt < max_attempts:
                    if bool(session.context.get("is_cancel_requested")):
                        raise asyncio.CancelledError("session cancel requested")
                    try:
                        debate_result, runtime_session_id = await self._execute_ai_debate(
                            session.context,
                            assets,
                            event_callback=_emit_and_record,
                            session_id=session_id,
                        )
                        debate_result = self._promote_judge_conclusion(
                            debate_result,
                            allow_peer_fallback=allow_peer_fallback_judgment,
                        )
                        if settings.DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION and not self._has_effective_llm_conclusion(
                            debate_result
                        ):
                            raise RuntimeError("未获得有效大模型结论，已拒绝生成兜底结论")
                        session.llm_session_id = runtime_session_id
                        break
                    except Exception as exc:
                        attempt += 1
                        error_text = str(exc).strip() or exc.__class__.__name__
                        lowered_error = error_text.lower()
                        if "timeout" in lowered_error:
                            timeout_failure = True
                        no_effective_conclusion = "未获得有效大模型结论" in error_text
                        degradable_missing_conclusion = self._should_degrade_missing_effective_conclusion(error_text)
                        if no_effective_conclusion and settings.DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION:
                            invalid_conclusion_failure = True
                        if degradable_missing_conclusion and attempt >= max_attempts:
                            debate_result = self._build_degraded_debate_result(
                                context=session.context,
                                assets=assets,
                                error_text=error_text,
                            )
                            await _emit_and_record(
                                {
                                    "type": "ai_debate_degraded",
                                    "phase": "debating",
                                    "attempt": attempt,
                                    "max_attempts": max_attempts,
                                    "error": error_text,
                                    "reason": "missing_effective_conclusion_due_to_timeout_or_rate_limit",
                                }
                            )
                            logger.warning(
                                "ai_debate_degraded_after_missing_effective_conclusion",
                                session_id=session_id,
                                error=error_text,
                            )
                            break
                        if (
                            no_effective_conclusion
                            and settings.DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION
                            and not degradable_missing_conclusion
                        ):
                            await _emit_and_record(
                                {
                                    "type": "debate_failed_no_effective_llm_conclusion",
                                    "phase": "debating",
                                    "attempt": attempt,
                                    "max_attempts": max_attempts,
                                    "error": error_text,
                                }
                            )
                            raise RuntimeError(error_text) from exc
                        if attempt >= max_attempts:
                            if settings.DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION:
                                raise RuntimeError(f"未获得有效大模型结论: {error_text}") from exc
                            debate_result = self._build_degraded_debate_result(
                                context=session.context,
                                assets=assets,
                                error_text=error_text,
                            )
                            await _emit_and_record(
                                {
                                    "type": "ai_debate_degraded",
                                    "phase": "debating",
                                    "attempt": attempt,
                                    "max_attempts": max_attempts,
                                    "error": error_text,
                                    "reason": "llm_unavailable_or_timeout",
                                }
                            )
                            logger.warning(
                                "ai_debate_degraded",
                                session_id=session_id,
                                error=error_text,
                            )
                            break
                        await self._transition_status(
                            session,
                            DebateStatus.RETRYING,
                            event_callback=_emit_and_record,
                            phase="debating",
                            trace_id=trace_id,
                        )
                        had_retry = True
                        await _emit_and_record(
                            {
                                "type": "debate_retry_scheduled",
                                "phase": "debating",
                                "attempt": attempt + 1,
                                "max_attempts": max_attempts,
                                "error": str(exc),
                            }
                        )
                        await self._transition_status(
                            session,
                            DebateStatus.WAITING,
                            event_callback=_emit_and_record,
                            phase="waiting",
                            trace_id=trace_id,
                        )
                        await asyncio.sleep(min(3, 2 ** attempt))
                        await self._transition_status(
                            session,
                            DebateStatus.DEBATING,
                            event_callback=_emit_and_record,
                            phase="debating",
                            trace_id=trace_id,
                        )
            
            # 更新辩论历史
            session.rounds = [
                DebateRound(
                    round_number=r.get("round_number", i),
                    phase=self._normalize_round_phase(r.get("phase", "analysis")),
                    agent_name=r.get("agent_name", ""),
                    agent_role=r.get("agent_role", ""),
                    model=r.get("model") or dict(settings.default_model_config),
                    input_message=r.get("input_message", ""),
                    output_content=r.get("output_content") or {},
                    confidence=r.get("confidence", 0),
                    started_at=datetime.fromisoformat(r["started_at"]) if r.get("started_at") else datetime.utcnow(),
                    completed_at=datetime.fromisoformat(r["completed_at"]) if r.get("completed_at") else None,
                )
                for i, r in enumerate(debate_result.get("debate_history", []))
            ]
            session.current_round = len(session.rounds)
            for round_ in session.rounds:
                await context_manager.append_round_context(
                    session_id=session_id,
                    round_context=round_.model_dump(mode="json"),
                )
            
            logger.info(
                "ai_debate_completed",
                session_id=session_id,
                confidence=debate_result.get("confidence", 0)
            )

            human_review_payload = debate_result.get("human_review") if isinstance(debate_result.get("human_review"), dict) else {}
            if (
                str(((session.context.get("deployment_profile") or {}).get("name") or "")).strip() == "production_governed"
                and bool(debate_result.get("awaiting_human_review") or False)
            ):
                await self._checkpoint_human_review(
                    session=session,
                    debate_result=debate_result,
                    assets=assets,
                    trace_id=trace_id,
                    event_callback=_emit_and_record,
                    review_reason=str(human_review_payload.get("reason") or debate_result.get("review_reason") or "需要人工审核确认"),
                    review_payload=dict(human_review_payload.get("payload") or {}),
                    resume_from_step=str(human_review_payload.get("resume_from_step") or "report_generation"),
                )
            
            # ========== 模块3: 报告生成 ==========
            logger.info("report_generation_started", session_id=session_id)
            await self._transition_status(
                session,
                DebateStatus.JUDGING,
                event_callback=_emit_and_record,
                phase=DebatePhase.JUDGMENT.value,
                trace_id=trace_id,
            )
            await _emit_and_record(
                {
                    "type": "phase_changed",
                    "phase": DebatePhase.JUDGMENT.value,
                    "status": session.status.value,
                }
            )
            
            report = await self._generate_report(
                session.context.get("incident", {}),
                debate_result,
                assets,
                event_callback=_emit_and_record,
            )
            await self._persist_report_snapshot(
                report,
                debate_session_id=session.id,
                trace_id=trace_id,
            )
            
            logger.info("report_generation_completed", session_id=session_id)

            review_state = self._get_human_review_state(session)
            if review_state:
                review_state.update(
                    {
                        "status": "completed",
                        "resumed_at": datetime.utcnow().isoformat(),
                    }
                )
                session.context["human_review"] = review_state
            session.context.pop("pending_review_checkpoint", None)
            
            # 更新会话状态
            await self._transition_status(
                session,
                DebateStatus.COMPLETED,
                event_callback=_emit_and_record,
                phase="completed",
                trace_id=trace_id,
            )
            session.completed_at = datetime.utcnow()
            await _emit_and_record(
                {
                    "type": "session_completed",
                    "session_id": session_id,
                    "status": session.status.value,
                }
            )
            session.context["event_log"] = event_log
            
            # 构建结果
            result = self._build_result(session, debate_result, report)
            await self._repository.save_session(session)
            await self._repository.save_result(result)
            
            logger.info(
                "debate_completed",
                session_id=session_id,
                confidence=result.confidence
            )
            latency_ms = max(
                0,
                int((datetime.utcnow() - execute_started_at).total_seconds() * 1000),
            )
            metrics_store.record_debate_result(
                status="completed",
                latency_ms=latency_ms,
                retried=had_retry,
                timeout=False,
                invalid_conclusion=False,
            )
            
            return result
        except HumanReviewRequired:
            session.context["event_log"] = event_log
            await self._repository.save_session(session)
            raise
        except asyncio.CancelledError:
            await self._transition_status(
                session,
                DebateStatus.CANCELLED,
                event_callback=_emit_and_record,
                phase="cancelled",
                trace_id=trace_id,
                force=True,
            )
            session.current_phase = None
            session.context["last_error"] = "session cancelled by request"
            await _emit_and_record(
                {
                    "type": "session_cancelled",
                    "session_id": session_id,
                    "status": session.status.value,
                    "reason": "cancel requested",
                }
            )
            session.context["event_log"] = event_log
            await self._repository.save_session(session)
            latency_ms = max(
                0,
                int((datetime.utcnow() - execute_started_at).total_seconds() * 1000),
            )
            metrics_store.record_debate_result(
                status="cancelled",
                latency_ms=latency_ms,
                retried=had_retry,
                timeout=False,
                invalid_conclusion=False,
            )
            raise
        except Exception as e:
            error_info = self._classify_error(str(e))
            await self._transition_status(
                session,
                DebateStatus.FAILED,
                event_callback=_emit_and_record,
                phase="failed",
                trace_id=trace_id,
                force=True,
            )
            session.current_phase = None
            session.context["last_error"] = str(error_info["error_message"])
            session.context["last_error_code"] = str(error_info["error_code"])
            session.context["last_error_recoverable"] = bool(error_info["recoverable"])
            session.context["last_error_retry_hint"] = str(error_info["retry_hint"])
            logger.error(
                "debate_failed",
                session_id=session_id,
                error=str(error_info["error_message"]),
                error_code=str(error_info["error_code"]),
                recoverable=bool(error_info["recoverable"]),
            )
            await _emit_and_record(
                {
                    "type": "phase_changed",
                    "phase": "failed",
                    "status": session.status.value,
                }
            )
            await _emit_and_record(
                {
                    "type": "session_failed",
                    "session_id": session_id,
                    "status": session.status.value,
                    "error": str(error_info["error_message"]),
                    "error_code": str(error_info["error_code"]),
                    "error_message": str(error_info["error_message"]),
                    "recoverable": bool(error_info["recoverable"]),
                    "retry_hint": str(error_info["retry_hint"]),
                }
            )
            session.context["event_log"] = event_log
            await self._repository.save_session(session)
            latency_ms = max(
                0,
                int((datetime.utcnow() - execute_started_at).total_seconds() * 1000),
            )
            error_message_lower = str(error_info["error_message"]).lower()
            metrics_store.record_debate_result(
                status="failed",
                latency_ms=latency_ms,
                retried=had_retry,
                timeout=timeout_failure or ("timeout" in error_message_lower),
                invalid_conclusion=invalid_conclusion_failure
                or ("无有效大模型结论" in str(error_info["error_message"])),
            )
            raise

    @staticmethod
    def _normalize_round_phase(raw_phase: Any) -> DebatePhase:
        """
        Normalize runtime phase values into DebatePhase enum.

        Runtime may emit internal phases like 'coordination' for orchestration
        turns. API/session model stores only analysis/critique/rebuttal/judgment.
        """
        text = str(raw_phase or "").strip().lower()
        mapping = {
            "analysis": DebatePhase.ANALYSIS,
            "analyzing": DebatePhase.ANALYSIS,
            "coordination": DebatePhase.COORDINATION,
            "orchestration": DebatePhase.COORDINATION,
            "debating": DebatePhase.ANALYSIS,
            "running": DebatePhase.ANALYSIS,
            "critique": DebatePhase.CRITIQUE,
            "critiquing": DebatePhase.CRITIQUE,
            "rebuttal": DebatePhase.REBUTTAL,
            "rebutting": DebatePhase.REBUTTAL,
            "judgment": DebatePhase.JUDGMENT,
            "judge": DebatePhase.JUDGMENT,
            "judging": DebatePhase.JUDGMENT,
            "verification": DebatePhase.VERIFICATION,
            "verify": DebatePhase.VERIFICATION,
        }
        if text in mapping:
            return mapping[text]
        logger.warning("unknown_round_phase_fallback_to_analysis", raw_phase=raw_phase)
        return DebatePhase.ANALYSIS

    async def _emit_seed_evidence_event(
        self,
        *,
        session: DebateSession,
        session_id: str,
        emit,
    ) -> None:
        """Emit early evidence so users can see investigation progress immediately."""
        context = session.context if isinstance(session.context, dict) else {}
        interface_mapping = context.get("interface_mapping") if isinstance(context.get("interface_mapping"), dict) else {}
        endpoint = interface_mapping.get("endpoint") if isinstance(interface_mapping.get("endpoint"), dict) else {}
        log_excerpt = str(context.get("log_content") or "").strip()
        log_excerpt = log_excerpt[:280] if log_excerpt else ""
        evidence = {
            "seed_sources": [
                "incident_log",
                "interface_mapping" if interface_mapping else "session_context",
            ],
            "log_excerpt": log_excerpt,
            "mapping": {
                "matched": bool(interface_mapping.get("matched")),
                "confidence": interface_mapping.get("confidence"),
                "method": endpoint.get("method"),
                "path": endpoint.get("path"),
                "service": endpoint.get("service"),
                "owner_team": interface_mapping.get("owner_team"),
                "owner": interface_mapping.get("owner"),
            },
        }
        first_evidence_at = datetime.utcnow().isoformat()
        session.context["first_evidence_at"] = first_evidence_at
        session.updated_at = datetime.utcnow()
        await self._repository.save_session(session)
        await emit(
            {
                "type": "first_evidence_ready",
                "phase": DebatePhase.ANALYSIS.value,
                "session_id": session_id,
                "first_evidence_at": first_evidence_at,
                "evidence": evidence,
            }
        )

    async def cancel_session(self, session_id: str, reason: str = "manual_cancel") -> bool:
        """取消会话，并把取消事件写入会话事件流。"""
        session = await self._repository.get_session(session_id)
        if not session:
            return False
        if session.status in {DebateStatus.COMPLETED, DebateStatus.CANCELLED}:
            return False

        session.context["is_cancel_requested"] = True
        session.context["cancel_reason"] = reason
        session.current_phase = None
        session.status = DebateStatus.CANCELLED
        session.updated_at = datetime.utcnow()
        trace_id = str(session.context.get("trace_id") or "").strip() or new_trace_id("deb")
        sequence = self._next_event_sequence(session)
        event = enrich_event(
            {
                "type": "session_cancelled",
                "session_id": session_id,
                "status": session.status.value,
                "reason": reason,
                "phase": "cancelled",
                "event_sequence": sequence,
            },
            trace_id=trace_id,
        )
        event_log = session.context.get("event_log")
        if not isinstance(event_log, list):
            event_log = []
        event_log.append({"timestamp": datetime.utcnow().isoformat(), "event": event})
        if len(event_log) > 500:
            del event_log[:-500]
        session.context["event_log"] = event_log
        await self._repository.save_session(session)
        return True

    def _get_human_review_state(self, session: DebateSession) -> Dict[str, Any]:
        """从会话上下文提取人工审核状态。"""
        payload = session.context.get("human_review")
        return dict(payload) if isinstance(payload, dict) else {}

    def _append_session_event(self, session: DebateSession, event: Dict[str, Any]) -> Dict[str, Any]:
        """向会话内置 `event_log` 追加一条标准化事件。"""
        trace_id = str(session.context.get("trace_id") or "").strip() or new_trace_id("deb")
        sequence = self._next_event_sequence(session)
        enriched = enrich_event(
            {
                **dict(event or {}),
                "session_id": session.id,
                "event_sequence": sequence,
            },
            trace_id=trace_id,
        )
        event_log = session.context.get("event_log")
        if not isinstance(event_log, list):
            event_log = []
        event_log.append({"timestamp": datetime.utcnow().isoformat(), "event": enriched})
        if len(event_log) > 500:
            del event_log[:-500]
        session.context["event_log"] = event_log
        return enriched

    async def approve_human_review(self, session_id: str, approver: str = "sre-oncall", comment: str = "") -> bool:
        """批准待人工审核的会话，但不直接恢复执行。"""
        session = await self._repository.get_session(session_id)
        if not session or session.status != DebateStatus.WAITING:
            return False
        review = self._get_human_review_state(session)
        if not review or str(review.get("status") or "") not in {"pending", "approved"}:
            return False
        review.update(
            {
                "status": "approved",
                "approver": str(approver or "sre-oncall"),
                "comment": str(comment or ""),
                "approved_at": datetime.utcnow().isoformat(),
            }
        )
        session.context["human_review"] = review
        self._append_session_event(
            session,
            {
                "type": "human_review_approved",
                "phase": DebatePhase.JUDGMENT.value,
                "status": session.status.value,
                "approver": review["approver"],
                "comment": review["comment"],
            },
        )
        session.updated_at = datetime.utcnow()
        await self._repository.save_session(session)
        return True

    async def reject_human_review(self, session_id: str, approver: str = "sre-oncall", reason: str = "") -> bool:
        """驳回待人工审核的会话，并推进到失败终态。"""
        session = await self._repository.get_session(session_id)
        if not session or session.status != DebateStatus.WAITING:
            return False
        review = self._get_human_review_state(session)
        if not review or str(review.get("status") or "") not in {"pending", "approved"}:
            return False
        review.update(
            {
                "status": "rejected",
                "approver": str(approver or "sre-oncall"),
                "rejection_reason": str(reason or "manual_reject"),
                "rejected_at": datetime.utcnow().isoformat(),
            }
        )
        session.context["human_review"] = review
        session.context.pop("pending_review_checkpoint", None)
        session.context["last_error"] = review["rejection_reason"]
        session.current_phase = None
        session.status = DebateStatus.FAILED
        session.updated_at = datetime.utcnow()
        self._append_session_event(
            session,
            {
                "type": "human_review_rejected",
                "phase": "failed",
                "status": session.status.value,
                "approver": review["approver"],
                "reason": review["rejection_reason"],
            },
        )
        await self._repository.save_session(session)
        return True

    async def _checkpoint_human_review(
        self,
        *,
        session: DebateSession,
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
        trace_id: str,
        event_callback,
        review_reason: str,
        review_payload: Dict[str, Any],
        resume_from_step: str,
    ) -> None:
        """在进入人工审核前保存恢复断点和中间快照。"""
        review_state = review_boundary.build_review_state(
            reason=str(review_reason or ""),
            payload=dict(review_payload or {}),
            resume_from_step=str(resume_from_step or "report_generation"),
        )
        session.context["human_review"] = review_state
        session.context["pending_review_checkpoint"] = {
            "debate_result": debate_result,
            "assets": assets,
        }
        session.current_phase = DebatePhase.JUDGMENT
        await self._transition_status(
            session,
            DebateStatus.WAITING,
            event_callback=event_callback,
            phase="waiting_review",
            trace_id=trace_id,
        )
        await self._emit_event(
            event_callback,
            self._append_session_event(
                session,
                {
                    "type": "human_review_requested",
                    "phase": DebatePhase.JUDGMENT.value,
                    "status": session.status.value,
                    "reason": review_state["reason"],
                    "resume_from_step": review_state["resume_from_step"],
                    "payload": review_state["payload"],
                },
            ),
        )
        session.updated_at = datetime.now(UTC)
        await self._repository.save_session(session)
        raise HumanReviewRequired(
            session.id,
            review_state["reason"],
            review_payload=review_state["payload"],
            resume_from_step=review_state["resume_from_step"],
        )
    
    async def _collect_assets(
        self,
        context: Dict[str, Any],
        event_callback=None,
    ) -> Dict[str, Any]:
        """
        采集三态资产
        
        Args:
            context: 上下文数据
            
        Returns:
            采集到的资产
        """
        incident = context.get("incident") or {}
        log_content = context.get("log_content")
        parsed_data = context.get("parsed_data") or {}
        metadata = incident.get("metadata") or {}
        symptom = incident.get("description") or incident.get("title") or ""
        
        await self._emit_event(
            event_callback,
            {
                "type": "asset_parallel_fetch_started",
                "phase": "asset_analysis",
            },
        )

        repo_url = metadata.get("repo_url")
        target_classes = parsed_data.get("key_classes", [])
        domain_name = metadata.get("domain_name")

        async def _collect_runtime() -> List[Any]:
            """执行收集运行时相关逻辑，并为当前模块提供可复用的处理能力。"""
            try:
                return await asset_collection_service.collect_runtime_assets(
                    log_content=log_content,
                    event_callback=event_callback,
                )
            except Exception as exc:  # noqa: BLE001
                await self._emit_event(
                    event_callback,
                    {
                        "type": "asset_parallel_fetch_failed",
                        "phase": "asset_analysis",
                        "asset_type": "runtime",
                        "error": str(exc),
                    },
                )
                return []

        async def _collect_dev() -> List[Any]:
            """执行收集dev相关逻辑，并为当前模块提供可复用的处理能力。"""
            try:
                return await asset_collection_service.collect_dev_assets(
                    repo_url=repo_url,
                    target_classes=target_classes,
                    event_callback=event_callback,
                )
            except Exception as exc:  # noqa: BLE001
                await self._emit_event(
                    event_callback,
                    {
                        "type": "asset_parallel_fetch_failed",
                        "phase": "asset_analysis",
                        "asset_type": "dev",
                        "error": str(exc),
                    },
                )
                return []

        async def _collect_design() -> List[Any]:
            """执行收集design相关逻辑，并为当前模块提供可复用的处理能力。"""
            try:
                return await asset_collection_service.collect_design_assets(
                    domain_name=domain_name,
                    event_callback=event_callback,
                )
            except Exception as exc:  # noqa: BLE001
                await self._emit_event(
                    event_callback,
                    {
                        "type": "asset_parallel_fetch_failed",
                        "phase": "asset_analysis",
                        "asset_type": "design",
                        "error": str(exc),
                    },
                )
                return []

        async def _collect_mapping() -> Dict[str, Any]:
            """执行收集mapping相关逻辑，并为当前模块提供可复用的处理能力。"""
            try:
                return await asset_service.locate_interface_context(
                    log_content=log_content or "",
                    symptom=symptom,
                )
            except Exception as exc:  # noqa: BLE001
                await self._emit_event(
                    event_callback,
                    {
                        "type": "asset_interface_mapping_failed",
                        "phase": "asset_analysis",
                        "error": str(exc),
                    },
                )
                return {"matched": False, "confidence": 0.0, "reason": f"mapping failed: {str(exc)[:120]}"}

        runtime_task = asyncio.create_task(_collect_runtime())
        dev_task = asyncio.create_task(_collect_dev())
        design_task = asyncio.create_task(_collect_design())
        mapping_task = asyncio.create_task(_collect_mapping())

        first_done, _ = await asyncio.wait(
            {runtime_task, dev_task, design_task, mapping_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for done_task in first_done:
            try:
                first_payload = done_task.result()
            except Exception:
                first_payload = []
            first_count = len(first_payload) if isinstance(first_payload, list) else (1 if first_payload else 0)
            await self._emit_event(
                event_callback,
                {
                    "type": "asset_first_batch_ready",
                    "phase": "asset_analysis",
                    "count": first_count,
                },
            )
            break

        runtime_assets, dev_assets, design_assets, interface_mapping = await asyncio.gather(
            runtime_task,
            dev_task,
            design_task,
            mapping_task,
        )
        normalized_mapping = self._normalize_interface_mapping_payload(interface_mapping)
        investigation_leads = self._build_investigation_leads(
            context=context,
            interface_mapping=normalized_mapping,
        )
        await self._emit_event(
            event_callback,
            {
                "type": "asset_interface_mapping_completed",
                "phase": "asset_analysis",
                "matched": normalized_mapping.get("matched", False),
                "confidence": normalized_mapping.get("confidence", 0.0),
                "domain": normalized_mapping.get("domain"),
                "aggregate": normalized_mapping.get("aggregate"),
                "owner_team": normalized_mapping.get("owner_team"),
                "api_count": len(list(investigation_leads.get("api_endpoints") or [])),
                "code_count": len(list(investigation_leads.get("code_artifacts") or [])),
                "table_count": len(list(investigation_leads.get("database_tables") or [])),
                "monitor_count": len(list(investigation_leads.get("monitor_items") or [])),
            },
        )
        
        return {
            "runtime_assets": [a.model_dump() for a in runtime_assets],
            "dev_assets": [a.model_dump() for a in dev_assets],
            "design_assets": [a.model_dump() for a in design_assets],
            "interface_mapping": normalized_mapping,
            "investigation_leads": investigation_leads,
        }
    
    async def _execute_ai_debate(
        self,
        context: Dict[str, Any],
        assets: Dict[str, Any],
        event_callback=None,
        session_id: Optional[str] = None,
    ) -> tuple[Dict[str, Any], Optional[str]]:
        """
        执行AI辩论分析
        
        Args:
            context: 上下文数据
            assets: 三态资产
            
        Returns:
            辩论结果
        """
        # 构建辩论上下文
        incident = context.get("incident") if isinstance(context.get("incident"), dict) else {}
        debate_context = {
            "incident": incident,
            "title": context.get("title") or incident.get("title") or "",
            "description": context.get("description") or incident.get("description") or "",
            "severity": context.get("severity") or incident.get("severity") or "",
            "service_name": context.get("service_name") or incident.get("service_name") or "",
            "log_content": context.get("log_content", ""),
            "parsed_data": context.get("parsed_data", {}),
            "runtime_assets": assets.get("runtime_assets", []),
            "dev_assets": assets.get("dev_assets", []),
            "design_assets": assets.get("design_assets", []),
            "interface_mapping": assets.get("interface_mapping", {}),
            "investigation_leads": assets.get("investigation_leads", {}),
            "trace_id": context.get("trace_id"),
            "execution_mode": context.get("execution_mode", "standard"),
            "runtime_strategy": context.get("runtime_strategy", {}),
            "deployment_profile": context.get("deployment_profile", {}),
        }
        
        debate_config = context.get("debate_config") if isinstance(context.get("debate_config"), dict) else {}
        configured_rounds = debate_config.get("max_rounds")
        try:
            max_rounds = int(configured_rounds) if configured_rounds is not None else int(settings.DEBATE_MAX_ROUNDS)
        except Exception:
            max_rounds = int(settings.DEBATE_MAX_ROUNDS)
        max_rounds = max(1, min(8, max_rounds))

        orchestrator = create_ai_debate_orchestrator(
            max_rounds=max_rounds,
            consensus_threshold=settings.DEBATE_CONSENSUS_THRESHOLD,
            analysis_depth_mode=debate_context.get("analysis_depth_mode"),
        )
        # 先把本次会话实际采用的深度模式和轮次发回前端，保证回放和报告读取同一套配置。

        async def _forward_event(event: Dict[str, Any]):
            """执行forward事件相关逻辑，并为当前模块提供可复用的处理能力。"""
            if session_id:
                await context_manager.update_session_context(
                    session_id,
                    {"last_event": event},
                )
            await self._emit_event(event_callback, event)

        await self._emit_event(
            event_callback,
            {
                "type": "debate_config_applied",
                "phase": "debating",
                "max_rounds": max_rounds,
                "analysis_depth_mode": str(debate_context.get("analysis_depth_mode") or "standard"),
                "consensus_threshold": settings.DEBATE_CONSENSUS_THRESHOLD,
            },
        )

        # 执行辩论流程
        strategy = debate_context.get("runtime_strategy")
        phase_mode = ""
        if isinstance(strategy, dict):
            phase_mode = str(strategy.get("phase_mode") or "").strip().lower()
        timeout_cap = 420
        if phase_mode == "economy":
            timeout_cap = 420
        elif phase_mode in {"fast_track", "failfast"}:
            timeout_cap = 360
        elif phase_mode == "standard":
            timeout_cap = 300
        debate_timeout = max(30, min(int(settings.DEBATE_TIMEOUT), timeout_cap))
        debate_context["session_timeout_seconds"] = float(debate_timeout)
        await self._emit_event(
            event_callback,
            {
                "type": "debate_timeout_budget_applied",
                "phase": "debating",
                "timeout_seconds": debate_timeout,
                "phase_mode": phase_mode or "standard",
            },
        )
        execute_task = asyncio.create_task(
            orchestrator.execute(
                debate_context,
                event_callback=_forward_event,
            )
        )
        try:
            result = await asyncio.wait_for(execute_task, timeout=debate_timeout)
        except asyncio.TimeoutError:
            recovered = self._recover_timeout_result(orchestrator=orchestrator, max_rounds=max_rounds)
            if recovered:
                recovered = self._promote_judge_conclusion(
                    recovered,
                    allow_peer_fallback=True,
                )
                if self._has_effective_llm_conclusion(recovered):
                    await self._emit_event(
                        event_callback,
                        {
                            "type": "debate_timeout_recovered",
                            "phase": "debating",
                            "timeout_seconds": debate_timeout,
                            "runtime_session_id": getattr(orchestrator, "session_id", None),
                        },
                    )
                    logger.warning(
                        "debate_timeout_recovered",
                        runtime_session_id=getattr(orchestrator, "session_id", None),
                        timeout_seconds=debate_timeout,
                    )
                    return recovered, getattr(orchestrator, "session_id", None)
            if not execute_task.done():
                execute_task.cancel()
                with suppress(Exception):
                    await execute_task
            raise

        return result, getattr(orchestrator, "session_id", None)

    @staticmethod
    def _normalize_text_list(value: Any, *, limit: int = 20) -> List[str]:
        """把字符串或列表规整为去重后的短文本列表。"""
        picks: List[str] = []
        if isinstance(value, list):
            items = value
        elif isinstance(value, str):
            items = re.split(r"[\n,;|]+", value)
        else:
            items = []
        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            picks.append(text[:180])
        return list(dict.fromkeys(picks))[:limit]

    def _normalize_interface_mapping_payload(self, payload: Any) -> Dict[str, Any]:
        """统一责任田映射结果中的接口、代码、表和监控字段。"""
        mapping = dict(payload or {}) if isinstance(payload, dict) else {}
        matched_endpoint = mapping.get("matched_endpoint")
        if not isinstance(matched_endpoint, dict):
            matched_endpoint = {}
        design_details = mapping.get("design_details")
        if not isinstance(design_details, dict):
            design_details = {}
        dependency_services = self._normalize_text_list(
            mapping.get("dependency_services") or design_details.get("domain_services") or [],
            limit=20,
        )
        monitor_items = self._normalize_text_list(mapping.get("monitor_items") or [], limit=20)
        code_artifacts: List[Dict[str, Any]] = []
        for item in list(mapping.get("code_artifacts") or [])[:20]:
            if isinstance(item, dict):
                path = str(item.get("path") or item.get("symbol") or "").strip()
                symbol = str(item.get("symbol") or item.get("path") or "").strip()
            else:
                path = str(item or "").strip()
                symbol = path
            if not path and not symbol:
                continue
            code_artifacts.append({"path": path[:240], "symbol": symbol[:180]})
        database_tables = self._normalize_text_list(
            mapping.get("database_tables") or mapping.get("db_tables") or [],
            limit=20,
        )
        mapping["matched_endpoint"] = matched_endpoint
        mapping["database_tables"] = database_tables
        mapping["db_tables"] = list(database_tables)
        mapping["dependency_services"] = dependency_services
        mapping["monitor_items"] = monitor_items
        mapping["code_artifacts"] = code_artifacts
        return mapping

    def _build_investigation_leads(
        self,
        *,
        context: Dict[str, Any],
        interface_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        从解析结果和责任田映射中构建标准化调查线索包。

        这一步是“主 Agent 下发方向”与“专家 Agent 自主扩展分析”之间的桥梁：
        统一整理接口、服务、类名、表名、监控项、依赖服务和 trace 线索，
        供后续命令注入、工具上下文构建和前端责任田展示复用。
        """
        parsed_data = context.get("parsed_data")
        parsed_data = parsed_data if isinstance(parsed_data, dict) else {}
        endpoint = interface_mapping.get("matched_endpoint")
        endpoint = endpoint if isinstance(endpoint, dict) else {}
        method = str(endpoint.get("method") or "").strip().upper()
        path = str(endpoint.get("path") or "").strip()
        interface_text = str(endpoint.get("interface") or "").strip()
        api_endpoints = self._normalize_text_list(
            [
                " ".join(part for part in [method, path] if part).strip(),
                interface_text,
                *(parsed_data.get("urls") or [] if isinstance(parsed_data.get("urls"), list) else []),
            ],
            limit=12,
        )
        service_names = self._normalize_text_list(
            [
                endpoint.get("service"),
                parsed_data.get("service"),
                *((interface_mapping.get("dependency_services") or [])[:6] if isinstance(interface_mapping.get("dependency_services"), list) else []),
            ],
            limit=12,
        )
        class_names = self._normalize_text_list(
            [
                *(parsed_data.get("class_names") or [] if isinstance(parsed_data.get("class_names"), list) else []),
                *(parsed_data.get("key_classes") or [] if isinstance(parsed_data.get("key_classes"), list) else []),
            ],
            limit=16,
        )
        code_artifacts: List[str] = []
        for item in list(interface_mapping.get("code_artifacts") or [])[:20]:
            if isinstance(item, dict):
                value = str(item.get("symbol") or item.get("path") or "").strip()
            else:
                value = str(item or "").strip()
            if value:
                code_artifacts.append(value[:240])
        trace_ids = self._normalize_text_list(
            [
                parsed_data.get("trace_id"),
                context.get("trace_id"),
            ],
            limit=6,
        )
        error_keywords = self._normalize_text_list(
            [
                parsed_data.get("error_type"),
                parsed_data.get("error_message"),
                parsed_data.get("exception_class"),
                parsed_data.get("exception_message"),
                *((parsed_data.get("exceptions") or [])[0].values() if isinstance((parsed_data.get("exceptions") or [None])[0], dict) else []),
            ],
            limit=12,
        )
        return {
            "api_endpoints": api_endpoints,
            "service_names": service_names,
            "code_artifacts": list(dict.fromkeys(code_artifacts))[:16],
            "class_names": class_names,
            "database_tables": self._normalize_text_list(interface_mapping.get("database_tables") or [], limit=20),
            "monitor_items": self._normalize_text_list(interface_mapping.get("monitor_items") or [], limit=16),
            "dependency_services": self._normalize_text_list(interface_mapping.get("dependency_services") or [], limit=16),
            "domain": str(interface_mapping.get("domain") or "").strip(),
            "aggregate": str(interface_mapping.get("aggregate") or "").strip(),
            "owner_team": str(interface_mapping.get("owner_team") or "").strip(),
            "owner": str(interface_mapping.get("owner") or "").strip(),
            "trace_ids": trace_ids,
            "error_keywords": error_keywords,
        }

    def _recover_timeout_result(
        self,
        *,
        orchestrator: Any,
        max_rounds: int,
    ) -> Optional[Dict[str, Any]]:
        """在辩论超时时尝试从 orchestrator 快照中恢复可用结果。"""
        try:
            history_cards = orchestrator._history_cards_snapshot(limit=20)
            payload = orchestrator._build_final_payload(
                history_cards=history_cards,
                consensus_reached=False,
                executed_rounds=max(1, int(max_rounds or 1)),
            )
            if not isinstance(payload, dict):
                return None
            debate_history = payload.get("debate_history")
            if not isinstance(debate_history, list) or not debate_history:
                return None
            return payload
        except Exception as exc:
            logger.warning("debate_timeout_recovery_failed", error=str(exc))
            return None

    @staticmethod
    def _is_placeholder_conclusion(text: str) -> bool:
        """判断结论是否只是占位或降级文案。"""
        summary = str(text or "").strip()
        if not summary:
            return True
        lowered = summary.lower()
        compact = lowered.replace(" ", "").replace("_", "")
        blocked_fragments = (
            "需要进一步分析",
            "further analysis",
            "llm 服务繁忙",
            "降级为规则分析",
            "调用超时，已降级继续",
            "调用异常，已降级继续",
            "未生成有效结论",
            "请重试分析流程",
            "待评估",
            "待确认",
            "待分析",
            "unknown",
        )
        if any(fragment in lowered for fragment in blocked_fragments):
            return True
        if compact in {"timeouterror", "runtimeerror", "errorexception", "unknownerror", "none", "null"}:
            return True
        if " " not in summary and len(summary) <= 64:
            token = summary.strip(":;,.").lower()
            if token.endswith("error") or token.endswith("exception"):
                return True
        return False

    @staticmethod
    def _coerce_confidence(value: Any, default: float = 0.0) -> float:
        """把任意置信度值安全收敛到 0~1 区间。"""
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return max(0.0, min(1.0, float(default)))

    @staticmethod
    def _has_meaningful_evidence(raw_items: Any) -> bool:
        """判断证据链里是否至少存在一条非空证据。"""
        if not isinstance(raw_items, list):
            return False
        for item in raw_items:
            if isinstance(item, dict):
                text = str(
                    item.get("description")
                    or item.get("evidence")
                    or item.get("summary")
                    or ""
                ).strip()
                if text:
                    return True
            else:
                text = str(item or "").strip()
                if text:
                    return True
        return False

    def _has_effective_llm_conclusion(self, debate_result: Dict[str, Any]) -> bool:
        """判断当前结果是否满足“有效大模型结论”门禁。"""
        if not isinstance(debate_result, dict):
            return False
        final_judgment = debate_result.get("final_judgment")
        if not isinstance(final_judgment, dict):
            return False
        root_cause = final_judgment.get("root_cause")
        if isinstance(root_cause, str):
            root_summary = root_cause
            root_confidence = 0.0
        elif isinstance(root_cause, dict):
            root_summary = str(root_cause.get("summary") or "").strip()
            root_confidence = self._coerce_confidence(root_cause.get("confidence"), default=0.0)
        else:
            root_summary = ""
            root_confidence = 0.0

        if self._is_placeholder_conclusion(root_summary):
            return False

        overall_confidence = self._coerce_confidence(debate_result.get("confidence"), default=0.0)
        has_effective_evidence = self._has_meaningful_evidence(final_judgment.get("evidence_chain"))
        judge_confidence_from_history = 0.0

        history = debate_result.get("debate_history")
        if isinstance(history, list):
            for row in reversed(history):
                if not isinstance(row, dict):
                    continue
                if str(row.get("agent_name") or "") != "JudgeAgent":
                    continue
                output = row.get("output_content") if isinstance(row.get("output_content"), dict) else {}
                judge_confidence = self._coerce_confidence(
                    row.get("confidence") or output.get("confidence"),
                    default=0.0,
                )
                judge_confidence_from_history = max(judge_confidence_from_history, judge_confidence)
                if has_effective_evidence and max(root_confidence, overall_confidence, judge_confidence) >= 0.45:
                    return True
                break

        if has_effective_evidence and max(root_confidence, overall_confidence) >= 0.45:
            return True

        # Quick/background modes may intentionally skip verification planning.
        # If Judge has produced a non-placeholder summary with moderate confidence,
        # treat it as an effective conclusion even when evidence_chain is concise.
        if max(root_confidence, overall_confidence, judge_confidence_from_history) >= 0.55:
            return True

        if max(root_confidence, overall_confidence) < 0.45:
            return False

        if not isinstance(history, list):
            return False

        for row in history:
            if not isinstance(row, dict):
                continue
            agent_name = str(row.get("agent_name") or "")
            if agent_name == "JudgeAgent":
                continue
            output = row.get("output_content")
            output = output if isinstance(output, dict) else {}
            conclusion = str(output.get("conclusion") or "").strip()
            if not conclusion:
                continue
            if "调用超时，已降级继续" in conclusion or "调用异常，已降级继续" in conclusion:
                continue
            confidence = self._coerce_confidence(
                row.get("confidence") or output.get("confidence"),
                default=0.0,
            )
            if confidence >= 0.55:
                return True
        return False

    def _promote_judge_conclusion(
        self,
        debate_result: Dict[str, Any],
        *,
        allow_peer_fallback: bool = False,
    ) -> Dict[str, Any]:
        """执行promote裁决结论相关逻辑，并为当前模块提供可复用的处理能力。"""
        if not isinstance(debate_result, dict):
            return debate_result
        history = debate_result.get("debate_history")
        if not isinstance(history, list):
            return debate_result

        final_judgment = debate_result.get("final_judgment")
        final_judgment = final_judgment if isinstance(final_judgment, dict) else {}
        root_cause = final_judgment.get("root_cause")
        root_summary = ""
        root_confidence = 0.0
        if isinstance(root_cause, dict):
            root_summary = str(root_cause.get("summary") or "").strip()
            root_confidence = self._coerce_confidence(root_cause.get("confidence"), default=0.0)
        elif isinstance(root_cause, str):
            root_summary = root_cause.strip()
        has_effective_evidence = self._has_meaningful_evidence(final_judgment.get("evidence_chain"))

        has_effective_root = (
            bool(root_summary)
            and not self._is_placeholder_conclusion(root_summary)
            and (root_confidence >= 0.45 or has_effective_evidence)
        )
        if has_effective_root:
            return debate_result

        for row in reversed(history):
            if not isinstance(row, dict):
                continue
            if str(row.get("agent_name") or "").strip() != "JudgeAgent":
                continue
            output = row.get("output_content")
            output = output if isinstance(output, dict) else {}
            judge_judgment = output.get("final_judgment")
            judge_judgment = judge_judgment if isinstance(judge_judgment, dict) else {}
            judge_root = judge_judgment.get("root_cause")
            judge_summary = ""
            if isinstance(judge_root, dict):
                judge_summary = str(judge_root.get("summary") or "").strip()
            elif isinstance(judge_root, str):
                judge_summary = judge_root.strip()
            if not judge_summary or self._is_placeholder_conclusion(judge_summary):
                continue
            merged = dict(debate_result)
            merged["final_judgment"] = judge_judgment
            merged["confidence"] = max(
                self._coerce_confidence(merged.get("confidence"), default=0.0),
                self._coerce_confidence(
                    row.get("confidence") or output.get("confidence"),
                    default=0.0,
                ),
            )
            return merged
        if allow_peer_fallback:
            for row in reversed(history):
                if not isinstance(row, dict):
                    continue
                agent_name = str(row.get("agent_name") or "").strip()
                if not agent_name or agent_name == "JudgeAgent":
                    continue
                output = row.get("output_content")
                output = output if isinstance(output, dict) else {}
                conclusion = str(output.get("conclusion") or "").strip()
                if not conclusion or self._is_placeholder_conclusion(conclusion):
                    continue
                confidence = self._coerce_confidence(
                    row.get("confidence") or output.get("confidence"),
                    default=0.0,
                )
                if confidence < 0.55:
                    continue
                evidence_chain = output.get("evidence_chain")
                if not isinstance(evidence_chain, list):
                    evidence_chain = []
                if not evidence_chain:
                    analysis_text = str(output.get("analysis") or "").strip()
                    if analysis_text:
                        evidence_chain = [
                            {
                                "type": "analysis",
                                "description": analysis_text[:220],
                                "source": agent_name,
                                "strength": "medium",
                            }
                        ]
                merged = dict(debate_result)
                merged["final_judgment"] = {
                    "root_cause": {
                        "summary": conclusion[:300],
                        "category": "peer_promoted",
                        "confidence": confidence,
                    },
                    "evidence_chain": evidence_chain,
                    "fix_recommendation": output.get("fix_recommendation")
                    if isinstance(output.get("fix_recommendation"), dict)
                    else {
                        "summary": "基于高置信专家结论先执行止血与验证，随后补充主裁决复核。",
                        "steps": ["执行止血动作", "补充指标与日志证据", "复跑裁决验证结论"],
                    },
                }
                merged["confidence"] = max(
                    self._coerce_confidence(merged.get("confidence"), default=0.0),
                    confidence,
                )
                return merged
        return debate_result

    def _build_degraded_debate_result(
        self,
        context: Dict[str, Any],
        assets: Dict[str, Any],
        error_text: str,
    ) -> Dict[str, Any]:
        """构造一份可审计的降级辩论结果。"""
        parsed_data = context.get("parsed_data") if isinstance(context.get("parsed_data"), dict) else {}
        interface_mapping = assets.get("interface_mapping") if isinstance(assets.get("interface_mapping"), dict) else {}
        endpoint = interface_mapping.get("matched_endpoint") if isinstance(interface_mapping.get("matched_endpoint"), dict) else {}
        method = str(endpoint.get("method") or "").strip().upper()
        path = str(endpoint.get("path") or "").strip()
        endpoint_text = " ".join([p for p in [method, path] if p]).strip() or "未知接口"
        exception_type = ""
        exception_message = ""
        exceptions = parsed_data.get("exceptions")
        if isinstance(exceptions, list) and exceptions and isinstance(exceptions[0], dict):
            exception_type = str(exceptions[0].get("type") or "")
            exception_message = str(exceptions[0].get("message") or "")
        if not exception_type:
            exception_type = str(parsed_data.get("exception_type") or "")
        if not exception_message:
            exception_message = str(parsed_data.get("exception_message") or "")
        summary_tail = "；".join([x for x in [exception_type, exception_message] if x]).strip("；")
        root_summary = (
            f"LLM 服务繁忙，已降级为规则分析：{endpoint_text} 存在故障，需结合连接池/事务/慢 SQL 指标进一步确认。"
        )
        if summary_tail:
            root_summary = f"{root_summary} 关键异常：{summary_tail[:160]}"

        owner_team = str(interface_mapping.get("owner_team") or "待确认")
        owner = str(interface_mapping.get("owner") or "待确认")

        return {
            "confidence": 0.32,
            "consensus_reached": False,
            "executed_rounds": 0,
            "final_judgment": {
                "root_cause": {
                    "summary": root_summary,
                    "category": "degraded_rule_based",
                    "confidence": 0.32,
                },
                "evidence_chain": [
                    {
                        "type": "system",
                        "description": f"LLM 调用超时或异常，触发降级策略：{error_text[:220]}",
                        "source": "degrade_fallback",
                        "location": endpoint_text,
                        "strength": "medium",
                    }
                ],
                "fix_recommendation": {
                    "summary": "先进行止血：限流/熔断并补采连接池与慢 SQL 指标，再重跑 AI 分析。",
                    "steps": [
                        "启用接口限流与超时熔断，防止故障扩大",
                        "采集连接池 active/idle/waiting 与慢 SQL 指标",
                        "完成指标补采后重新触发一次自动分析",
                    ],
                    "code_changes_required": False,
                    "rollback_recommended": False,
                    "testing_requirements": ["故障链路回放", "连接池压力验证"],
                },
                "impact_analysis": {
                    "affected_services": [str(endpoint.get("service") or "unknown-service")],
                    "business_impact": "分析阶段出现外部模型限流，自动分析可靠性下降",
                    "affected_users": "故障接口相关用户",
                },
                "risk_assessment": {
                    "risk_level": "high",
                    "risk_factors": ["LLM 服务限流", "当前结论为降级结果，证据不足"],
                    "mitigation_suggestions": [
                        "降低并发或错峰触发分析任务",
                        "补采运行指标后重试分析",
                    ],
                },
            },
            "decision_rationale": {
                "key_factors": [
                    "外部 LLM 429/超时触发降级",
                    "仍命中责任田映射，可输出最小可执行止血建议",
                ],
                "reasoning": "为避免会话长时间无响应，系统已自动返回降级结论。",
            },
            "action_items": [
                {"priority": 1, "action": "执行止血策略并观察 15 分钟", "owner": owner_team},
                {"priority": 2, "action": "补采关键指标后重新分析", "owner": owner},
            ],
            "responsible_team": {"team": owner_team, "owner": owner},
            "dissenting_opinions": [],
            "debate_history": [],
        }

    async def _emit_event(self, event_callback, event: Dict[str, Any]) -> None:
        """安全触发事件回调；回调为空时直接跳过。"""
        if not event_callback:
            return
        maybe_coro = event_callback(event)
        if hasattr(maybe_coro, "__await__"):
            await maybe_coro

    async def _transition_status(
        self,
        session: DebateSession,
        next_status: DebateStatus,
        event_callback=None,
        phase: Optional[str] = None,
        trace_id: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """执行一次受状态机约束的状态迁移，并按需发出状态变化事件。"""
        current = session.status
        allowed = self._STATUS_TRANSITIONS.get(current, set())
        if not force and next_status != current and next_status not in allowed:
            raise RuntimeError(f"invalid status transition: {current.value} -> {next_status.value}")
        session.status = next_status
        session.updated_at = datetime.utcnow()
        await self._repository.save_session(session)
        if event_callback:
            sequence = self._next_event_sequence(session)
            await self._emit_event(
                event_callback,
                enrich_event(
                    {
                        "type": "status_changed",
                        "phase": phase or str(session.current_phase.value if session.current_phase else ""),
                        "session_id": session.id,
                        "event_sequence": sequence,
                        "from_status": current.value,
                        "status": next_status.value,
                    },
                    trace_id=trace_id or str(session.context.get("trace_id") or "").strip() or new_trace_id("deb"),
                ),
            )
    
    async def _generate_report(
        self,
        incident: Dict[str, Any],
        debate_result: Dict[str, Any],
        assets: Dict[str, Any],
        event_callback=None,
    ) -> Dict[str, Any]:
        """
        生成分析报告
        
        Args:
            incident: 故障事件
            debate_result: 辩论结果
            assets: 三态资产
            
        Returns:
            生成的报告
        """
        report = await report_generation_service.generate_report(
            incident=incident,
            debate_result=debate_result,
            assets=assets,
            format="markdown",
            event_callback=event_callback,
        )
        
        return report

    async def _persist_report_snapshot(
        self,
        report: Dict[str, Any],
        debate_session_id: str,
        trace_id: Optional[str] = None,
    ) -> None:
        """把报告快照持久化到报告仓储；失败时仅记录 warning。"""
        try:
            # 延迟导入，避免 debate_service <-> report_service 的模块循环依赖。
            from app.services.report_service import report_service

            await report_service.save_generated_report(
                report=report,
                debate_session_id=debate_session_id,
            )
        except Exception as exc:
            logger.warning(
                "report_snapshot_persist_failed",
                debate_session_id=debate_session_id,
                error=str(exc),
                trace_id=trace_id,
            )
    
    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        """获取辩论结果"""
        result = await self._repository.get_result(session_id)
        if not result:
            return None
        if not self._is_placeholder_root_cause(result.root_cause):
            return result

        session = await self._repository.get_session(session_id)
        if not session or not session.rounds:
            return result

        best = self._pick_best_round_conclusion(session.rounds)
        if not best:
            return result

        result.root_cause = str(best.get("conclusion") or result.root_cause)
        result.root_cause_category = str(best.get("category") or result.root_cause_category or "multi_agent_inference")
        try:
            result.confidence = max(float(result.confidence or 0.0), float(best.get("confidence") or 0.0))
        except Exception:
            pass

        if not result.evidence_chain:
            evidence_items = []
            for item in best.get("evidence_chain") or []:
                text = str(item or "").strip()
                if not text:
                    continue
                evidence_items.append(
                    EvidenceItem(
                        type="analysis",
                        description=text[:220],
                        source=str(best.get("agent_name") or "ai_debate"),
                        location=None,
                        strength="medium",
                    )
                )
            result.evidence_chain = evidence_items

        if not result.fix_recommendation:
            result.fix_recommendation = FixRecommendation(
                summary=str(best.get("conclusion") or "")[:260],
                steps=[{"summary": str(best.get("summary") or best.get("conclusion") or "")[:180]}],
                code_changes_required=bool(best.get("agent_name") in {"CodeAgent", "RebuttalAgent"}),
                rollback_recommended=False,
                testing_requirements=["回归故障链路", "压力与超时测试"],
            )

        await self._repository.save_result(result)
        return result

    def _is_placeholder_root_cause(self, root_cause: Optional[str]) -> bool:
        """判断根因文本是否为空或明显属于占位描述。"""
        text = str(root_cause or "").strip()
        if not text:
            return True
        if "需要进一步分析" in text:
            return True
        if text in {"待评估", "待确认", "unknown", "Unknown"}:
            return True
        return False

    def _pick_best_round_conclusion(self, rounds: List[DebateRound]) -> Optional[Dict[str, Any]]:
        """从历史轮次中挑出最可信的一条专家结论作为兜底。"""
        best: Optional[Dict[str, Any]] = None
        best_score = -1.0
        category_map = {
            "CodeAgent": "code_or_resource",
            "LogAgent": "runtime_log",
            "DomainAgent": "domain_mapping",
            "DatabaseAgent": "database_signal",
            "CriticAgent": "peer_review",
            "RebuttalAgent": "peer_review",
        }
        for round_ in rounds:
            if round_.agent_name == "JudgeAgent":
                continue
            output = round_.output_content if isinstance(round_.output_content, dict) else {}
            conclusion = str(output.get("conclusion") or "").strip()
            if not conclusion:
                continue
            if "调用超时，已降级继续" in conclusion or "调用异常，已降级继续" in conclusion:
                continue
            if "需要进一步分析" in conclusion:
                continue
            try:
                score = float(round_.confidence or output.get("confidence") or 0.0)
            except Exception:
                score = 0.0
            if score < 0.55:
                continue
            if score > best_score:
                best_score = score
                best = {
                    "agent_name": round_.agent_name,
                    "summary": str(output.get("analysis") or "")[:200],
                    "conclusion": conclusion[:300],
                    "confidence": score,
                    "evidence_chain": output.get("evidence_chain") if isinstance(output.get("evidence_chain"), list) else [],
                    "category": category_map.get(round_.agent_name, "multi_agent_inference"),
                }
        return best
    
    async def list_sessions(
        self,
        incident_id: Optional[str] = None,
        status: Optional[DebateStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """列出辩论会话"""
        sessions = await self._repository.list_sessions()
        
        # 过滤
        if incident_id:
            sessions = [s for s in sessions if s.incident_id == incident_id]
        if status:
            sessions = [s for s in sessions if s.status == status]
        
        # 排序
        sessions.sort(key=lambda x: x.created_at, reverse=True)
        
        # 分页
        total = len(sessions)
        start = (page - 1) * page_size
        end = start + page_size
        items = sessions[start:end]
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    
    def _build_result(
        self,
        session: DebateSession,
        flow_result: Dict[str, Any],
        report: Dict[str, Any]
    ) -> DebateResult:
        """构建辩论结果"""
        _ = report
        flow_result = flow_result if isinstance(flow_result, dict) else {}
        final_judgment = flow_result.get("final_judgment", {})
        final_judgment = final_judgment if isinstance(final_judgment, dict) else {}

        root_cause_raw = final_judgment.get("root_cause", {})
        if isinstance(root_cause_raw, dict):
            root_cause_summary = extract_readable_text(
                root_cause_raw.get("summary"),
                fallback="Unknown",
                max_len=420,
            ) or "Unknown"
            root_cause_category = root_cause_raw.get("category")
            root_cause_confidence = self._coerce_confidence(root_cause_raw.get("confidence"), default=0.0)
        else:
            root_cause_summary = extract_readable_text(root_cause_raw, fallback="Unknown", max_len=420) or "Unknown"
            root_cause_category = None
            root_cause_confidence = 0.0

        # 构建证据链（统一标准化模型）
        evidence_chain: List[EvidenceItem] = []
        normalized_evidence = normalize_evidence_items(final_judgment.get("evidence_chain"))
        cross_source_passed = has_cross_source_evidence(normalized_evidence)
        if not cross_source_passed:
            normalized_evidence.extend(self._fallback_cross_source_evidence(session))
            cross_source_passed = has_cross_source_evidence(normalized_evidence)
        dedup_keys = set()
        deduped_evidence: List[Dict[str, Any]] = []
        for item in normalized_evidence:
            key = f"{item.get('source')}|{item.get('description')}|{item.get('source_ref')}"
            if key in dedup_keys:
                continue
            dedup_keys.add(key)
            deduped_evidence.append(item)
        for item in deduped_evidence:
            evidence_chain.append(
                EvidenceItem(
                    evidence_id=str(item.get("evidence_id") or "") or None,
                    type=str(item.get("type") or "unknown"),
                    description=str(item.get("description") or ""),
                    source=str(item.get("source") or "ai_debate"),
                    source_ref=str(item.get("source_ref") or "") or None,
                    location=item.get("location"),
                    strength=str(item.get("strength") or "medium"),
                )
            )

        # 构建修复建议
        fix_rec = final_judgment.get("fix_recommendation", {})
        if isinstance(fix_rec, str):
            fix_rec = {"summary": fix_rec}
        if not isinstance(fix_rec, dict):
            fix_rec = {}
        raw_steps = fix_rec.get("steps", [])
        steps: List[Dict[str, Any]] = []
        if isinstance(raw_steps, list):
            for item in raw_steps:
                if isinstance(item, dict):
                    steps.append(item)
                else:
                    text = str(item or "").strip()
                    if text:
                        steps.append({"summary": text})
        fix_recommendation = None
        if fix_rec:
            fix_recommendation = FixRecommendation(
                summary=extract_readable_text(
                    fix_rec.get("summary", ""),
                    fallback=str(fix_rec.get("summary", "")),
                    max_len=420,
                ),
                steps=steps,
                code_changes_required=bool(fix_rec.get("code_changes_required", False)),
                rollback_recommended=bool(fix_rec.get("rollback_recommended", False)),
                testing_requirements=[
                    str(x) for x in (fix_rec.get("testing_requirements") or []) if str(x).strip()
                ],
            )

        # 构建影响分析
        impact = final_judgment.get("impact_analysis", {})
        if not isinstance(impact, dict):
            impact = {}
        impact_analysis = None
        if impact:
            impact_analysis = ImpactAnalysis(
                affected_services=[
                    str(x) for x in (impact.get("affected_services") or []) if str(x).strip()
                ],
                affected_users=impact.get("affected_users"),
                business_impact=impact.get("business_impact"),
                estimated_recovery_time=impact.get("estimated_recovery_time")
            )

        # 构建风险评估
        risk = final_judgment.get("risk_assessment", {})
        if not isinstance(risk, dict):
            risk = {}
        risk_assessment = None
        if risk:
            risk_level = str(risk.get("risk_level") or "medium")
            if risk_level not in {"critical", "high", "medium", "low"}:
                risk_level = "medium"
            risk_assessment = RiskAssessment(
                risk_level=risk_level,
                risk_factors=[str(x) for x in (risk.get("risk_factors") or []) if str(x).strip()],
                mitigation_suggestions=[
                    str(x) for x in (risk.get("mitigation_suggestions") or []) if str(x).strip()
                ],
            )

        # 构建责任信息
        responsible = flow_result.get("responsible_team", {})
        if isinstance(responsible, str):
            responsible = {"team": responsible, "owner": None}
        if not isinstance(responsible, dict):
            responsible = {}

        # 兼容 list[str] / str 形式的行动项与异议项
        action_items_raw = flow_result.get("action_items", [])
        action_items: List[Dict[str, Any]] = []
        if isinstance(action_items_raw, list):
            for item in action_items_raw:
                if isinstance(item, dict):
                    action_items.append(item)
                else:
                    text = str(item or "").strip()
                    if text:
                        action_items.append({"summary": extract_readable_text(text, fallback=text, max_len=220)})

        dissent_raw = flow_result.get("dissenting_opinions", [])
        dissenting_opinions: List[Dict[str, Any]] = []
        if isinstance(dissent_raw, list):
            for item in dissent_raw:
                if isinstance(item, dict):
                    dissenting_opinions.append(item)
                else:
                    text = str(item or "").strip()
                    if text:
                        dissenting_opinions.append({"summary": extract_readable_text(text, fallback=text, max_len=220)})

        verification_plan_raw = flow_result.get("verification_plan")
        if not isinstance(verification_plan_raw, list):
            verification_plan_raw = final_judgment.get("verification_plan")
        verification_plan: List[Dict[str, Any]] = []
        if isinstance(verification_plan_raw, list):
            for item in verification_plan_raw:
                if isinstance(item, dict):
                    verification_plan.append(item)
                else:
                    text = str(item or "").strip()
                    if text:
                        verification_plan.append({"objective": text, "steps": [text]})

        confidence = self._coerce_confidence(flow_result.get("confidence"), default=0.0)
        has_effective_root = (
            bool(root_cause_summary)
            and not self._is_placeholder_conclusion(root_cause_summary)
            and (root_cause_confidence >= 0.45 or bool(evidence_chain))
        )
        if has_effective_root:
            # 中文注释：runtime 顶层 confidence 可能仍是旧的保守门槛值，
            # 但 final_judgment.root_cause.confidence 才是 Judge 收口后的最新裁决。
            # 这里优先保留“有效根因”的置信度，避免结果出库时被错误压回 0.45。
            confidence = max(confidence, root_cause_confidence)
        elif confidence <= 0.0 and isinstance(root_cause_raw, dict):
            confidence = root_cause_confidence
        if confidence <= 0.0:
            judge_turn = next(
                (turn for turn in reversed(session.rounds) if turn.agent_name == "JudgeAgent"),
                None,
            )
            if judge_turn:
                confidence = self._coerce_confidence(judge_turn.confidence, default=0.0)
        confidence = max(0.0, min(1.0, confidence))
        claim_graph = final_judgment.get("claim_graph")
        claim_graph = claim_graph if isinstance(claim_graph, dict) else {}

        scoring = causal_score(
            root_cause=root_cause_summary,
            evidence=[item.model_dump(mode="json") for item in evidence_chain],
            confidence=confidence,
        )
        topology_scoring = self._topology_propagation_score(
            session=session,
            evidence=[item.model_dump(mode="json") for item in evidence_chain],
        )
        self_consistency = self._self_consistency_score(session)
        root_cause_candidates = self._build_root_cause_candidates(
            session=session,
            primary_root_cause=root_cause_summary,
            primary_confidence=confidence,
            evidence_chain=evidence_chain,
            topology_score=float(topology_scoring.get("topology_score") or 0.0),
        )
        action_items.append(
            {
                "type": "quality_gate",
                "summary": (
                    f"相关性分={scoring['relevance_score']}, 因果分={scoring['causality_score']}, "
                    f"拓扑传播分={topology_scoring['topology_score']}, 自一致性={self_consistency['score']}"
                ),
                "details": {
                    "causal_score": scoring,
                    "topology_score": topology_scoring,
                    "self_consistency": self_consistency,
                    "cross_source_evidence": cross_source_passed,
                },
            }
        )
        if not cross_source_passed:
            action_items.append(
                {
                    "type": "evidence_gate",
                    "summary": "跨源证据不足：建议补充日志+代码/领域/指标证据后重跑分析",
                    "details": {
                        "required_sources": ["runtime_log", "code_repo|domain_asset|metrics_snapshot"],
                        "status": "failed",
                    },
                }
            )

        return DebateResult(
            session_id=session.id,
            incident_id=session.incident_id,
            root_cause=root_cause_summary,
            root_cause_category=root_cause_category,
            confidence=confidence,
            cross_source_passed=cross_source_passed,
            root_cause_candidates=root_cause_candidates,
            evidence_chain=evidence_chain,
            claim_graph=claim_graph,
            fix_recommendation=fix_recommendation,
            impact_analysis=impact_analysis,
            risk_assessment=risk_assessment,
            responsible_team=responsible.get("team"),
            responsible_owner=responsible.get("owner"),
            action_items=action_items,
            verification_plan=verification_plan,
            dissenting_opinions=dissenting_opinions,
            debate_history=session.rounds
        )

    def _topology_propagation_score(
        self,
        *,
        session: DebateSession,
        evidence: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """基于上下游传播关系估算拓扑传播得分。"""
        return score_topology_propagation(
            context=session.context if isinstance(session.context, dict) else {},
            evidence=evidence,
        )

    def _build_root_cause_candidates(
        self,
        *,
        session: DebateSession,
        primary_root_cause: str,
        primary_confidence: float,
        evidence_chain: List[EvidenceItem],
        topology_score: float,
    ) -> List[RootCauseCandidate]:
        """从主结论和专家轮次中构建 Top-K 根因候选。"""
        candidates: List[RootCauseCandidate] = []
        seen = set()
        base_refs = [
            str(item.evidence_id or "").strip()
            for item in evidence_chain[:3]
            if str(item.evidence_id or "").strip()
        ]

        primary_summary = str(primary_root_cause or "").strip()
        if primary_summary:
            primary_adj = max(0.0, min(1.0, float(primary_confidence) * 0.8 + float(topology_score) * 0.2))
            conflict_points: List[str] = []
            uncertainty_sources: List[str] = []
            if primary_adj < 0.7:
                uncertainty_sources.append("主结论置信度仍在中等区间")
            if topology_score < 0.4:
                uncertainty_sources.append("拓扑传播证据偏弱")
            candidates.append(
                RootCauseCandidate(
                    rank=1,
                    summary=primary_summary,
                    source_agent="JudgeAgent",
                    confidence=round(primary_adj, 3),
                    confidence_interval=[round(max(0.0, primary_adj - 0.12), 3), round(min(1.0, primary_adj + 0.1), 3)],
                    evidence_refs=base_refs,
                    evidence_coverage_count=len(base_refs),
                    conflict_points=conflict_points,
                    uncertainty_sources=uncertainty_sources,
                )
            )
            seen.add(primary_summary.lower())

        interim: List[Dict[str, Any]] = []
        for round_ in reversed(session.rounds):
            if round_.agent_name == "JudgeAgent":
                continue
            output = round_.output_content if isinstance(round_.output_content, dict) else {}
            text = str(output.get("conclusion") or output.get("analysis") or "").strip()
            if not text:
                continue
            compact = text.lower()
            if compact in seen:
                continue
            score = self._coerce_confidence(round_.confidence, default=0.0)
            if score <= 0.0:
                score = self._coerce_confidence(output.get("confidence"), default=0.0)
            score = max(0.0, min(1.0, score * 0.75 + topology_score * 0.25))
            interim.append(
                {
                    "summary": text[:260],
                    "agent": round_.agent_name,
                    "confidence": round(score, 3),
                    "interval": [round(max(0.0, score - 0.15), 3), round(min(1.0, score + 0.1), 3)],
                }
            )
            seen.add(compact)
            if len(interim) >= 8:
                break

        interim.sort(key=lambda row: float(row.get("confidence") or 0.0), reverse=True)
        rank_base = len(candidates)
        for idx, row in enumerate(interim[: max(0, 3 - rank_base)], start=1):
            candidates.append(
                RootCauseCandidate(
                    rank=rank_base + idx,
                    summary=str(row.get("summary") or ""),
                    source_agent=str(row.get("agent") or ""),
                    confidence=float(row.get("confidence") or 0.0),
                    confidence_interval=list(row.get("interval") or []),
                    evidence_refs=base_refs,
                    evidence_coverage_count=len(base_refs),
                    conflict_points=[
                        "与主结论存在竞争解释，尚需更多跨源证据"
                    ],
                    uncertainty_sources=[
                        "来自单一Agent结论，尚未完成全链路交叉验证"
                    ],
                )
            )
        return candidates

    def _fallback_cross_source_evidence(self, session: DebateSession) -> List[Dict[str, Any]]:
        """正式证据链不足时，从专家轮次里补一份跨源证据兜底。"""
        fallback: List[Dict[str, Any]] = []
        for round_ in reversed(session.rounds):
            output = round_.output_content if isinstance(round_.output_content, dict) else {}
            conclusion = str(output.get("conclusion") or "").strip()
            if not conclusion:
                continue
            source = "ai_debate"
            if round_.agent_name == "LogAgent":
                source = "runtime_log"
            elif round_.agent_name in {"CodeAgent", "ChangeAgent"}:
                source = "code_repo"
            elif round_.agent_name == "DatabaseAgent":
                source = "database_snapshot"
            elif round_.agent_name == "DomainAgent":
                source = "domain_asset"
            elif round_.agent_name == "MetricsAgent":
                source = "metrics_snapshot"
            fallback.append(
                {
                    "evidence_id": f"fallback_{round_.agent_name}_{round_.round_number}",
                    "type": round_.phase.value if hasattr(round_.phase, "value") else str(round_.phase),
                    "description": conclusion[:200],
                    "source": source,
                    "source_ref": f"{round_.agent_name}:{round_.round_number}",
                    "location": None,
                    "strength": "medium",
                }
            )
            if len(fallback) >= 4:
                break
        return fallback

    def _self_consistency_score(self, session: DebateSession) -> Dict[str, Any]:
        """根据 Judge/Critic/Rebuttal 结论一致性估算自洽得分。"""
        conclusions: List[str] = []
        for round_ in session.rounds:
            if round_.agent_name in {"JudgeAgent", "CriticAgent", "RebuttalAgent"}:
                output = round_.output_content if isinstance(round_.output_content, dict) else {}
                conclusion = str(output.get("conclusion") or output.get("analysis") or "").strip()
                if conclusion:
                    conclusions.append(conclusion)
        if not conclusions:
            return {"score": 0.0, "votes": 0}
        normalized = [text.replace(" ", "").lower()[:80] for text in conclusions]
        counts: Dict[str, int] = {}
        for item in normalized:
            counts[item] = counts.get(item, 0) + 1
        top_votes = max(counts.values()) if counts else 0
        score = top_votes / max(1, len(normalized))
        return {"score": round(score, 3), "votes": len(normalized)}


# 全局实例
debate_service = DebateService()
