"""
辩论服务
Debate Service

整合资产采集、AI辩论分析和报告生成三个核心模块。
"""

import asyncio
import uuid
from datetime import datetime
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
)
from app.models.incident import Incident
from app.flows.debate_flow import ai_debate_orchestrator
from app.flows.context import context_manager
from app.services.asset_collection_service import asset_collection_service
from app.services.asset_service import asset_service
from app.services.report_generation_service import report_generation_service
from app.config import settings
from app.core.event_schema import enrich_event, new_trace_id
from app.repositories.debate_repository import (
    DebateRepository,
    InMemoryDebateRepository,
    FileDebateRepository,
)

logger = structlog.get_logger()


class DebateService:
    """辩论服务 - 整合三大核心模块"""

    _STATUS_TRANSITIONS: Dict[DebateStatus, set[DebateStatus]] = {
        DebateStatus.PENDING: {DebateStatus.RUNNING, DebateStatus.CANCELLED, DebateStatus.FAILED},
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
        DebateStatus.ANALYZING: {
            DebateStatus.RUNNING,
            DebateStatus.DEBATING,
            DebateStatus.WAITING,
            DebateStatus.RETRYING,
            DebateStatus.CANCELLED,
            DebateStatus.FAILED,
        },
        DebateStatus.DEBATING: {
            DebateStatus.RUNNING,
            DebateStatus.JUDGING,
            DebateStatus.WAITING,
            DebateStatus.RETRYING,
            DebateStatus.CANCELLED,
            DebateStatus.FAILED,
        },
        DebateStatus.JUDGING: {
            DebateStatus.COMPLETED,
            DebateStatus.WAITING,
            DebateStatus.RETRYING,
            DebateStatus.CANCELLED,
            DebateStatus.FAILED,
        },
        DebateStatus.WAITING: {DebateStatus.RUNNING, DebateStatus.ANALYZING, DebateStatus.DEBATING, DebateStatus.RETRYING, DebateStatus.CANCELLED, DebateStatus.FAILED},
        DebateStatus.RETRYING: {DebateStatus.RUNNING, DebateStatus.ANALYZING, DebateStatus.DEBATING, DebateStatus.JUDGING, DebateStatus.WAITING, DebateStatus.CANCELLED, DebateStatus.FAILED},
        DebateStatus.FAILED: {DebateStatus.RETRYING, DebateStatus.CANCELLED},
        DebateStatus.CANCELLED: {DebateStatus.RETRYING},
        DebateStatus.COMPLETED: set(),
        DebateStatus.CRITIQUING: {DebateStatus.REBUTTING, DebateStatus.JUDGING, DebateStatus.FAILED},
        DebateStatus.REBUTTING: {DebateStatus.JUDGING, DebateStatus.FAILED},
    }
    
    def __init__(self, repository: Optional[DebateRepository] = None):
        self._repository = repository or (
            FileDebateRepository()
            if settings.LOCAL_STORE_BACKEND == "file"
            else InMemoryDebateRepository()
        )
    
    async def create_session(
        self,
        incident: Incident,
        max_rounds: Optional[int] = None,
    ) -> DebateSession:
        """
        创建辩论会话
        
        Args:
            incident: 关联的故障事件
            
        Returns:
            创建的辩论会话
        """
        session_id = f"deb_{uuid.uuid4().hex[:8]}"
        
        debate_config: Dict[str, Any] = {}
        if max_rounds is not None:
            debate_config["max_rounds"] = max(1, min(8, int(max_rounds)))

        session_context: Dict[str, Any] = {
            "incident": incident.model_dump(),
            "log_content": incident.log_content,
            "exception_stack": incident.exception_stack,
            "parsed_data": incident.parsed_data,
        }
        if debate_config:
            session_context["debate_config"] = debate_config

        session = DebateSession(
            id=session_id,
            incident_id=incident.id,
            status=DebateStatus.PENDING,
            context=session_context,
        )
        
        await self._repository.save_session(session)
        
        logger.info(
            "debate_session_created",
            session_id=session_id,
            incident_id=incident.id,
            max_rounds=debate_config.get("max_rounds"),
        )
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        """获取辩论会话"""
        return await self._repository.get_session(session_id)
    
    async def execute_debate(
        self,
        session_id: str,
        event_callback=None,
    ) -> DebateResult:
        """
        执行完整的辩论流程
        
        整合三大模块：
        1. 资产采集
        2. AI辩论分析
        3. 报告生成
        
        Args:
            session_id: 会话ID
            
        Returns:
            辩论结果
        """
        session = await self._repository.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        if session.status == DebateStatus.COMPLETED:
            existed = await self._repository.get_result(session_id)
            if existed:
                return existed
        if session.status == DebateStatus.CANCELLED:
            raise RuntimeError(f"Session {session_id} is cancelled")
        
        trace_id = str(session.context.get("trace_id") or "").strip() or new_trace_id("deb")
        session.context["trace_id"] = trace_id
        session.context["is_cancel_requested"] = False
        await self._transition_status(
            session,
            DebateStatus.RUNNING,
            event_callback=event_callback,
            phase="running",
            trace_id=trace_id,
        )
        await self._transition_status(
            session,
            DebateStatus.ANALYZING,
            event_callback=event_callback,
            phase=DebatePhase.ANALYSIS.value,
            trace_id=trace_id,
        )
        await context_manager.init_session_context(session_id, session.context)
        event_log: List[Dict[str, Any]] = []

        async def _emit_and_record(event: Dict[str, Any]) -> None:
            payload = enrich_event(event, trace_id=trace_id)
            event_log.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "event": payload,
                }
            )
            if len(event_log) > 500:
                del event_log[:-500]
            # 持续落库事件，保证分析中会话在刷新/历史页也可查看过程记录
            session.context["event_log"] = event_log
            session.updated_at = datetime.utcnow()
            await self._repository.save_session(session)
            await self._emit_event(event_callback, payload)

        await _emit_and_record(
            {
                "type": "session_started",
                "session_id": session_id,
                "status": session.status.value,
                "phase": DebatePhase.ANALYSIS.value,
            }
        )
        
        try:
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

            max_attempts = 2
            attempt = 0
            debate_result: Dict[str, Any] = {}
            while attempt < max_attempts:
                if bool(session.context.get("is_cancel_requested")):
                    raise asyncio.CancelledError("session cancel requested")
                try:
                    debate_result = await self._execute_ai_debate(
                        session.context,
                        assets,
                        event_callback=_emit_and_record,
                        session_id=session_id,
                    )
                    if settings.DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION and not self._has_effective_llm_conclusion(
                        debate_result
                    ):
                        raise RuntimeError("未获得有效大模型结论，已拒绝生成兜底结论")
                    session.llm_session_id = getattr(ai_debate_orchestrator, "session_id", None)
                    break
                except Exception as exc:
                    attempt += 1
                    error_text = str(exc).strip() or exc.__class__.__name__
                    no_effective_conclusion = "未获得有效大模型结论" in error_text
                    if no_effective_conclusion and settings.DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION:
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
                    phase=DebatePhase(r.get("phase", "analysis")),
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
            
            return result
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
            raise
        except Exception as e:
            await self._transition_status(
                session,
                DebateStatus.FAILED,
                event_callback=_emit_and_record,
                phase="failed",
                trace_id=trace_id,
                force=True,
            )
            session.current_phase = None
            session.context["last_error"] = str(e)
            logger.error("debate_failed", session_id=session_id, error=str(e))
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
                    "error": str(e),
                }
            )
            session.context["event_log"] = event_log
            await self._repository.save_session(session)
            raise

    async def cancel_session(self, session_id: str, reason: str = "manual_cancel") -> bool:
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
        event = enrich_event(
            {
                "type": "session_cancelled",
                "session_id": session_id,
                "status": session.status.value,
                "reason": reason,
                "phase": "cancelled",
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
        
        # 采集运行态资产
        runtime_assets = await asset_collection_service.collect_runtime_assets(
            log_content=log_content,
            event_callback=event_callback,
        )
        
        # 采集开发态资产（如果有代码仓库信息）
        repo_url = metadata.get("repo_url")
        target_classes = parsed_data.get("key_classes", [])
        dev_assets = await asset_collection_service.collect_dev_assets(
            repo_url=repo_url,
            target_classes=target_classes,
            event_callback=event_callback,
        )
        
        # 采集设计态资产
        domain_name = metadata.get("domain_name")
        design_assets = await asset_collection_service.collect_design_assets(
            domain_name=domain_name,
            event_callback=event_callback,
        )

        interface_mapping = await asset_service.locate_interface_context(
            log_content=log_content or "",
            symptom=symptom,
        )
        await self._emit_event(
            event_callback,
            {
                "type": "asset_interface_mapping_completed",
                "phase": "asset_analysis",
                "matched": interface_mapping.get("matched", False),
                "confidence": interface_mapping.get("confidence", 0.0),
                "domain": interface_mapping.get("domain"),
                "aggregate": interface_mapping.get("aggregate"),
                "owner_team": interface_mapping.get("owner_team"),
            },
        )
        
        return {
            "runtime_assets": [a.model_dump() for a in runtime_assets],
            "dev_assets": [a.model_dump() for a in dev_assets],
            "design_assets": [a.model_dump() for a in design_assets],
            "interface_mapping": interface_mapping,
        }
    
    async def _execute_ai_debate(
        self,
        context: Dict[str, Any],
        assets: Dict[str, Any],
        event_callback=None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行AI辩论分析
        
        Args:
            context: 上下文数据
            assets: 三态资产
            
        Returns:
            辩论结果
        """
        # 构建辩论上下文
        debate_context = {
            "log_content": context.get("log_content", ""),
            "parsed_data": context.get("parsed_data", {}),
            "runtime_assets": assets.get("runtime_assets", []),
            "dev_assets": assets.get("dev_assets", []),
            "design_assets": assets.get("design_assets", []),
            "interface_mapping": assets.get("interface_mapping", {}),
            "trace_id": context.get("trace_id"),
        }
        
        debate_config = context.get("debate_config") if isinstance(context.get("debate_config"), dict) else {}
        configured_rounds = debate_config.get("max_rounds")
        try:
            max_rounds = int(configured_rounds) if configured_rounds is not None else int(settings.DEBATE_MAX_ROUNDS)
        except Exception:
            max_rounds = int(settings.DEBATE_MAX_ROUNDS)
        max_rounds = max(1, min(8, max_rounds))

        # 将配置下发到编排器
        ai_debate_orchestrator.max_rounds = max_rounds
        ai_debate_orchestrator.consensus_threshold = settings.DEBATE_CONSENSUS_THRESHOLD

        async def _forward_event(event: Dict[str, Any]):
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
                "consensus_threshold": settings.DEBATE_CONSENSUS_THRESHOLD,
            },
        )

        # 执行辩论流程
        debate_timeout = max(30, min(int(settings.DEBATE_TIMEOUT), 300))
        result = await asyncio.wait_for(
            ai_debate_orchestrator.execute(
                debate_context,
                event_callback=_forward_event,
            ),
            timeout=debate_timeout,
        )
        
        return result

    def _has_effective_llm_conclusion(self, debate_result: Dict[str, Any]) -> bool:
        if not isinstance(debate_result, dict):
            return False
        final_judgment = debate_result.get("final_judgment")
        if not isinstance(final_judgment, dict):
            return False
        root_cause = final_judgment.get("root_cause")
        root_cause = root_cause if isinstance(root_cause, dict) else {}
        summary = str(root_cause.get("summary") or "").strip()
        if not summary:
            return False
        lowered_summary = summary.lower()
        if "需要进一步分析" in summary or "further analysis" in lowered_summary:
            return False
        if summary in {"待评估", "待确认", "unknown", "待分析"}:
            return False

        history = debate_result.get("debate_history")
        if not isinstance(history, list) or not history:
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
            try:
                confidence = float(row.get("confidence") or output.get("confidence") or 0.0)
            except Exception:
                confidence = 0.0
            if confidence >= 0.55:
                return True
        return False

    def _build_degraded_debate_result(
        self,
        context: Dict[str, Any],
        assets: Dict[str, Any],
        error_text: str,
    ) -> Dict[str, Any]:
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
        current = session.status
        allowed = self._STATUS_TRANSITIONS.get(current, set())
        if not force and next_status != current and next_status not in allowed:
            raise RuntimeError(f"invalid status transition: {current.value} -> {next_status.value}")
        session.status = next_status
        session.updated_at = datetime.utcnow()
        await self._repository.save_session(session)
        if event_callback:
            await self._emit_event(
                event_callback,
                enrich_event(
                    {
                        "type": "status_changed",
                        "phase": phase or str(session.current_phase.value if session.current_phase else ""),
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
        text = str(root_cause or "").strip()
        if not text:
            return True
        if "需要进一步分析" in text:
            return True
        if text in {"待评估", "待确认", "unknown", "Unknown"}:
            return True
        return False

    def _pick_best_round_conclusion(self, rounds: List[DebateRound]) -> Optional[Dict[str, Any]]:
        best: Optional[Dict[str, Any]] = None
        best_score = -1.0
        category_map = {
            "CodeAgent": "code_or_resource",
            "LogAgent": "runtime_log",
            "DomainAgent": "domain_mapping",
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
            root_cause_summary = str(root_cause_raw.get("summary") or "Unknown").strip() or "Unknown"
            root_cause_category = root_cause_raw.get("category")
        else:
            root_cause_summary = str(root_cause_raw or "Unknown").strip() or "Unknown"
            root_cause_category = None

        # 构建证据链（兼容 evidence_chain 内字符串项）
        evidence_chain: List[EvidenceItem] = []
        evidence_items = final_judgment.get("evidence_chain", [])
        if not isinstance(evidence_items, list):
            evidence_items = []
        for e in evidence_items:
            if isinstance(e, dict):
                description = (
                    e.get("description")
                    or e.get("evidence")
                    or e.get("summary")
                    or ""
                )
                strength = str(e.get("strength") or "medium")
                if strength not in {"strong", "medium", "weak"}:
                    strength = "medium"
                evidence_chain.append(
                    EvidenceItem(
                        type=str(e.get("type") or "unknown"),
                        description=str(description),
                        source=str(e.get("source") or "ai_debate"),
                        location=e.get("location") or e.get("code_location"),
                        strength=strength,
                    )
                )
            else:
                text = str(e or "").strip()
                if text:
                    evidence_chain.append(
                        EvidenceItem(
                            type="text",
                            description=text,
                            source="ai_debate",
                            location=None,
                            strength="medium",
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
                summary=str(fix_rec.get("summary", "")),
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
                        action_items.append({"summary": text})

        dissent_raw = flow_result.get("dissenting_opinions", [])
        dissenting_opinions: List[Dict[str, Any]] = []
        if isinstance(dissent_raw, list):
            for item in dissent_raw:
                if isinstance(item, dict):
                    dissenting_opinions.append(item)
                else:
                    text = str(item or "").strip()
                    if text:
                        dissenting_opinions.append({"summary": text})

        try:
            confidence = float(flow_result.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        return DebateResult(
            session_id=session.id,
            incident_id=session.incident_id,
            root_cause=root_cause_summary,
            root_cause_category=root_cause_category,
            confidence=confidence,
            evidence_chain=evidence_chain,
            fix_recommendation=fix_recommendation,
            impact_analysis=impact_analysis,
            risk_assessment=risk_assessment,
            responsible_team=responsible.get("team"),
            responsible_owner=responsible.get("owner"),
            action_items=action_items,
            dissenting_opinions=dissenting_opinions,
            debate_history=session.rounds
        )


# 全局实例
debate_service = DebateService()
