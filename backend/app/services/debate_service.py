"""
辩论服务
Debate Service

整合资产采集、AI辩论分析和报告生成三个核心模块。
"""

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
from app.repositories.debate_repository import (
    DebateRepository,
    InMemoryDebateRepository,
    FileDebateRepository,
)

logger = structlog.get_logger()


class DebateService:
    """辩论服务 - 整合三大核心模块"""
    
    def __init__(self, repository: Optional[DebateRepository] = None):
        self._repository = repository or (
            FileDebateRepository()
            if settings.LOCAL_STORE_BACKEND == "file"
            else InMemoryDebateRepository()
        )
    
    async def create_session(self, incident: Incident) -> DebateSession:
        """
        创建辩论会话
        
        Args:
            incident: 关联的故障事件
            
        Returns:
            创建的辩论会话
        """
        session_id = f"deb_{uuid.uuid4().hex[:8]}"
        
        session = DebateSession(
            id=session_id,
            incident_id=incident.id,
            status=DebateStatus.PENDING,
            context={
                "incident": incident.model_dump(),
                "log_content": incident.log_content,
                "exception_stack": incident.exception_stack,
                "parsed_data": incident.parsed_data,
            }
        )
        
        await self._repository.save_session(session)
        
        logger.info(
            "debate_session_created",
            session_id=session_id,
            incident_id=incident.id
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
        
        # 更新状态
        session.status = DebateStatus.ANALYZING
        session.updated_at = datetime.utcnow()
        await context_manager.init_session_context(session_id, session.context)
        event_log: List[Dict[str, Any]] = []

        async def _emit_and_record(event: Dict[str, Any]) -> None:
            if not event.get("timestamp"):
                event["timestamp"] = datetime.utcnow().isoformat()
            event_log.append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "event": event,
                }
            )
            if len(event_log) > 500:
                del event_log[:-500]
            # 持续落库事件，保证分析中会话在刷新/历史页也可查看过程记录
            session.context["event_log"] = event_log
            session.updated_at = datetime.utcnow()
            await self._repository.save_session(session)
            await self._emit_event(event_callback, event)

        await _emit_and_record(
            {
                "type": "session_started",
                "session_id": session_id,
                "status": session.status.value,
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
            session.status = DebateStatus.DEBATING
            await _emit_and_record(
                {
                    "type": "phase_changed",
                    "phase": "debating",
                    "status": session.status.value,
                }
            )
            
            debate_result = await self._execute_ai_debate(
                session.context,
                assets,
                event_callback=_emit_and_record,
                session_id=session_id,
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
            session.status = DebateStatus.JUDGING
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
            
            logger.info("report_generation_completed", session_id=session_id)
            
            # 更新会话状态
            session.status = DebateStatus.COMPLETED
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
            
        except Exception as e:
            session.status = DebateStatus.FAILED
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
            "dev_assets": assets.get("dev_assets", []),
            "design_assets": assets.get("design_assets", []),
            "interface_mapping": assets.get("interface_mapping", {}),
        }
        
        # 将配置下发到编排器
        ai_debate_orchestrator.max_rounds = settings.DEBATE_MAX_ROUNDS
        ai_debate_orchestrator.consensus_threshold = settings.DEBATE_CONSENSUS_THRESHOLD

        async def _forward_event(event: Dict[str, Any]):
            if session_id:
                await context_manager.update_session_context(
                    session_id,
                    {"last_event": event},
                )
            await self._emit_event(event_callback, event)

        # 执行辩论流程
        result = await ai_debate_orchestrator.execute(
            debate_context,
            event_callback=_forward_event,
        )
        
        return result

    async def _emit_event(self, event_callback, event: Dict[str, Any]) -> None:
        if not event_callback:
            return
        maybe_coro = event_callback(event)
        if hasattr(maybe_coro, "__await__"):
            await maybe_coro
    
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
    
    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        """获取辩论结果"""
        return await self._repository.get_result(session_id)
    
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
