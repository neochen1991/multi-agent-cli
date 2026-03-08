"""辩论会话 API。

负责创建会话、同步/异步执行、多种恢复与取消操作，以及结果、谱系、回放等查询接口。
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status, BackgroundTasks
from pydantic import BaseModel, Field

from app.models.debate import (
    DebateSession,
    DebateResult,
    DebateStatus,
    DebatePhase,
    DebateRound,
)
from app.models.incident import IncidentStatus, IncidentUpdate
from app.runtime.task_registry import runtime_task_registry
from app.services.debate_service import HumanReviewRequired, debate_service
from app.services.incident_service import incident_service
from app.core.task_queue import task_queue
from app.config import settings
from app.runtime.trace_lineage import lineage_recorder, replay_session_lineage
from app.runtime_serve import normalize_execution_mode
from app.runtime.langgraph.output_truncation import get_output_reference

router = APIRouter()


# ==================== API 数据模型 ====================

class DebateSessionResponse(BaseModel):
    """辩论会话基础响应。"""
    id: str
    incident_id: str
    status: str
    current_phase: Optional[str]
    current_round: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        """提供模型配置项，统一对象序列化与字段行为。"""
        from_attributes = True


class DebateRoundResponse(BaseModel):
    """单轮 Agent 执行结果响应。"""
    round_number: int
    phase: str
    agent_name: str
    agent_role: str
    model: Optional[Dict[str, Any]] = None
    input_message: Optional[str] = None
    output_content: Optional[Dict[str, Any]] = None
    confidence: float
    started_at: datetime
    completed_at: Optional[datetime] = None


class EvidenceItemResponse(BaseModel):
    """证据项响应。"""
    type: str
    description: str
    source: str
    location: Optional[str]
    strength: str


class RootCauseCandidateResponse(BaseModel):
    """根因候选摘要响应。"""

    rank: int
    summary: str
    source_agent: Optional[str] = None
    confidence: float
    confidence_interval: List[float] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)


class FixRecommendationResponse(BaseModel):
    """修复建议响应。"""
    summary: str
    steps: List[Dict[str, Any]]
    code_changes_required: bool
    rollback_recommended: bool
    testing_requirements: List[str]


class ImpactAnalysisResponse(BaseModel):
    """影响分析响应。"""
    affected_services: List[str]
    affected_users: Optional[str]
    business_impact: Optional[str]
    estimated_recovery_time: Optional[str]


class RiskAssessmentResponse(BaseModel):
    """风险评估响应。"""
    risk_level: str
    risk_factors: List[str]
    mitigation_suggestions: List[str]


class DebateResultResponse(BaseModel):
    """辩论最终结果响应。"""
    session_id: str
    incident_id: str
    root_cause: str
    root_cause_category: Optional[str]
    confidence: float
    root_cause_candidates: List[RootCauseCandidateResponse]
    evidence_chain: List[EvidenceItemResponse]
    fix_recommendation: Optional[FixRecommendationResponse]
    impact_analysis: Optional[ImpactAnalysisResponse]
    risk_assessment: Optional[RiskAssessmentResponse]
    responsible_team: Optional[str]
    responsible_owner: Optional[str]
    action_items: List[Dict[str, Any]]
    dissenting_opinions: List[Dict[str, Any]]
    created_at: datetime


class DebateDetailResponse(DebateSessionResponse):
    """辩论详情响应，附带轮次历史和上下文快照。"""
    rounds: List[DebateRoundResponse]
    context: Dict[str, Any]


class DebateListResponse(BaseModel):
    """分页辩论会话列表响应。"""
    items: List[DebateSessionResponse]
    total: int
    page: int
    page_size: int


class TaskResponse(BaseModel):
    """异步任务状态响应。"""

    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CancelResponse(BaseModel):
    """取消会话后的响应。"""

    session_id: str
    cancelled: bool


class HumanReviewActionRequest(BaseModel):
    """人工审核批准请求。"""

    approver: str = "sre-oncall"
    comment: str = ""


class HumanReviewRejectRequest(BaseModel):
    """人工审核驳回请求。"""

    approver: str = "sre-oncall"
    reason: str = ""


class HumanReviewActionResponse(BaseModel):
    """人工审核动作执行结果。"""

    session_id: str
    success: bool
    review_status: str
    message: str


class LineageResponse(BaseModel):
    """会话谱系查询响应。"""

    session_id: str
    resolved_session_id: Optional[str] = None
    records: int
    events: int
    tools: int
    agents: List[str]
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


class ReplayResponse(BaseModel):
    """会话关键流程回放响应。"""

    session_id: str
    resolved_session_id: Optional[str] = None
    count: int
    rendered_steps: List[str]
    summary: Dict[str, Any]
    timeline: List[Dict[str, Any]]
    filters: Dict[str, Any] = Field(default_factory=dict)
    key_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)


class OutputReferenceResponse(BaseModel):
    """截断输出引用回查结果。"""

    ref_id: str
    found: bool
    session_id: str = ""
    category: str = ""
    content: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


# ==================== API 端点 ====================

@router.post(
    "/",
    response_model=DebateSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建辩论会话",
    description="为指定故障创建辩论会话"
)
async def create_debate_session(
    incident_id: str,
    background_tasks: BackgroundTasks,
    max_rounds: Optional[int] = Query(
        default=None,
        ge=1,
        le=8,
        description="本次辩论最大轮数（可选，默认使用系统配置）",
    ),
    mode: str = Query(
        default="standard",
        pattern="^(standard|quick|background|async)$",
        description="会话执行模式：standard|quick|background|async",
    ),
    deployment_profile: str = Query(
        default="",
        pattern="^(|baseline|skill_enabled|investigation_full|production_governed)$",
        description="可选部署图模板：baseline|skill_enabled|investigation_full|production_governed",
    ),
):
    """为指定 incident 创建辩论会话，并同步把 incident 状态推进到分析中。"""
    # 先校验 incident 存在，避免创建孤儿会话。
    incident = await incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    # 创建会话时会把执行模式、最大轮次和部署图模板写入 session.context。
    session = await debate_service.create_session(
        incident,
        max_rounds=max_rounds,
        execution_mode=normalize_execution_mode(mode).value,
        deployment_profile=deployment_profile,
    )
    
    # incident 与 debate session 之间保持显式关联，便于前端从 incident 详情跳到会话详情。
    await incident_service.update_incident(
        incident_id,
        IncidentUpdate(
            status=IncidentStatus.ANALYZING,
            debate_session_id=session.id,
        )
    )
    
    return DebateSessionResponse(
        id=session.id,
        incident_id=session.incident_id,
        status=session.status.value,
        current_phase=session.current_phase.value if session.current_phase else None,
        current_round=session.current_round,
        created_at=session.created_at,
        updated_at=session.updated_at,
        completed_at=session.completed_at,
    )


@router.post(
    "/{session_id}/execute",
    response_model=DebateResultResponse,
    summary="执行辩论流程",
    description="执行完整的辩论流程并返回结果"
)
async def execute_debate(
    session_id: str,
    retry_failed_only: bool = Query(
        default=False,
        description="是否仅重试失败的 Agent（当前为兼容参数，默认 false）",
    ),
):
    """同步执行完整辩论流程，并在成功后回填 incident 结果。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found"
        )
    
    if session.status == DebateStatus.COMPLETED:
        # 已完成会话直接返回已保存结果，避免重复执行。
        result = await debate_service.get_result(session_id)
        if result:
            return _build_result_response(result)
    
    try:
        result = await debate_service.execute_debate(
            session_id,
            retry_failed_only=retry_failed_only,
        )
        
        # 成功完成后，把裁决结果写回 incident，保证首页和列表页状态一致。
        await incident_service.update_incident(
            session.incident_id,
            IncidentUpdate(
                status=IncidentStatus.RESOLVED,
                root_cause=result.root_cause,
                fix_suggestion=result.fix_recommendation.summary if result.fix_recommendation else None,
                impact_analysis=result.impact_analysis.model_dump() if result.impact_analysis else None,
            )
        )
        
        return _build_result_response(result)
    except HumanReviewRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": exc.reason or "human review required",
                "review_status": "pending",
                "resume_from_step": exc.resume_from_step,
                "review_payload": exc.review_payload,
            },
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Debate execution failed: {str(e)}"
        )


@router.post(
    "/{session_id}/execute-async",
    response_model=TaskResponse,
    summary="异步执行辩论流程",
    description="提交异步辩论任务，返回 task_id",
)
async def execute_debate_async(
    session_id: str,
    retry_failed_only: bool = Query(
        default=False,
        description="是否仅重试失败的 Agent（当前为兼容参数，默认 false）",
    ),
):
    """以任务队列方式异步执行辩论流程。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )

    async def _run():
        """异步任务主体，负责运行辩论并同步 runtime_task_registry/incident 状态。"""
        try:
            await runtime_task_registry.mark_started(
                session_id=session_id,
                task_type="debate",
                trace_id=str((session.context or {}).get("trace_id") or ""),
            )
            result = await asyncio.wait_for(
                debate_service.execute_debate(
                    session_id,
                    retry_failed_only=retry_failed_only,
                ),
                timeout=max(60, int(settings.DEBATE_TIMEOUT or 600)),
            )
            await runtime_task_registry.mark_done(session_id, status="completed")
            await incident_service.update_incident(
                session.incident_id,
                IncidentUpdate(
                    status=IncidentStatus.RESOLVED,
                    root_cause=result.root_cause,
                    fix_suggestion=(
                        result.fix_recommendation.summary if result.fix_recommendation else None
                    ),
                    impact_analysis=(
                        result.impact_analysis.model_dump() if result.impact_analysis else None
                    ),
                ),
            )
            return {
                "session_id": result.session_id,
                "incident_id": result.incident_id,
                "confidence": result.confidence,
            }
        except HumanReviewRequired as exc:
            await runtime_task_registry.mark_waiting_review(
                session_id,
                review_reason=exc.reason,
                resume_from_step=exc.resume_from_step,
                phase="waiting_review",
                event_type="human_review_requested",
            )
            return {
                "session_id": session_id,
                "status": "waiting_review",
                "review_status": "pending",
                "review_reason": exc.reason,
                "resume_from_step": exc.resume_from_step,
            }
        except Exception as exc:
            await runtime_task_registry.mark_done(session_id, status="failed", error=str(exc))
            await incident_service.update_incident(
                session.incident_id,
                IncidentUpdate(
                    status=IncidentStatus.CLOSED,
                    fix_suggestion=str(exc)[:260],
                ),
            )
            raise

    task_id = task_queue.submit(_run, timeout_seconds=max(60, int(settings.DEBATE_TIMEOUT or 600)))
    return TaskResponse(task_id=task_id, status="pending")


@router.post(
    "/{session_id}/execute-background",
    response_model=TaskResponse,
    summary="后台执行辩论流程",
    description="提交后台辩论任务（适用于断连后继续）",
)
async def execute_debate_background(
    session_id: str,
    retry_failed_only: bool = Query(
        default=False,
        description="是否仅重试失败的 Agent（当前为兼容参数，默认 false）",
    ),
):
    """以后台恢复模式执行辩论，适用于前端断开后继续跑完整流程。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )

    context = dict(session.context or {})
    context["execution_mode"] = normalize_execution_mode("background").value
    session.context = context
    await debate_service.update_session(session)

    async def _run():
        """后台模式任务主体。"""
        try:
            await runtime_task_registry.mark_started(
                session_id=session_id,
                task_type="debate",
                trace_id=str((session.context or {}).get("trace_id") or ""),
            )
            result = await asyncio.wait_for(
                debate_service.execute_debate(
                    session_id,
                    retry_failed_only=retry_failed_only,
                ),
                timeout=max(60, int(settings.DEBATE_TIMEOUT or 600)),
            )
            await runtime_task_registry.mark_done(session_id, status="completed")
            await incident_service.update_incident(
                session.incident_id,
                IncidentUpdate(
                    status=IncidentStatus.RESOLVED,
                    root_cause=result.root_cause,
                    fix_suggestion=(
                        result.fix_recommendation.summary if result.fix_recommendation else None
                    ),
                    impact_analysis=(
                        result.impact_analysis.model_dump() if result.impact_analysis else None
                    ),
                ),
            )
            return {
                "session_id": result.session_id,
                "incident_id": result.incident_id,
                "confidence": result.confidence,
            }
        except HumanReviewRequired as exc:
            await runtime_task_registry.mark_waiting_review(
                session_id,
                review_reason=exc.reason,
                resume_from_step=exc.resume_from_step,
                phase="waiting_review",
                event_type="human_review_requested",
            )
            return {
                "session_id": session_id,
                "status": "waiting_review",
                "review_status": "pending",
                "review_reason": exc.reason,
                "resume_from_step": exc.resume_from_step,
            }
        except Exception as exc:
            await runtime_task_registry.mark_done(session_id, status="failed", error=str(exc))
            await incident_service.update_incident(
                session.incident_id,
                IncidentUpdate(
                    status=IncidentStatus.CLOSED,
                    fix_suggestion=str(exc)[:260],
                ),
            )
            raise

    task_id = task_queue.submit(_run, timeout_seconds=max(60, int(settings.DEBATE_TIMEOUT or 600)))
    return TaskResponse(task_id=task_id, status="pending")


@router.post(
    "/{session_id}/cancel",
    response_model=CancelResponse,
    summary="取消辩论任务",
    description="将会话标记为取消状态（若运行中会由 WS 任务协同中断）",
)
async def cancel_debate(session_id: str):
    """取消指定辩论会话，并在成功时同步关闭 incident。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )
    cancelled = await debate_service.cancel_session(session_id, reason="api_cancel")
    if cancelled:
        await incident_service.update_incident(
            session.incident_id,
            IncidentUpdate(
                status=IncidentStatus.CLOSED,
                fix_suggestion="analysis cancelled",
            ),
        )
    return CancelResponse(session_id=session_id, cancelled=cancelled)


@router.post(
    "/{session_id}/human-review/approve",
    response_model=HumanReviewActionResponse,
    summary="批准人工审核",
    description="将待人工审核会话标记为已批准，允许后续 resume",
)
async def approve_human_review(session_id: str, body: HumanReviewActionRequest):
    """批准待人工审核的会话。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )
    approved = await debate_service.approve_human_review(
        session_id,
        approver=body.approver,
        comment=body.comment,
    )
    if not approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no pending human review to approve",
        )
    await runtime_task_registry.mark_review_decision(
        session_id,
        review_status="approved",
        status="waiting_review",
    )
    return HumanReviewActionResponse(
        session_id=session_id,
        success=True,
        review_status="approved",
        message="human review approved",
    )


@router.post(
    "/{session_id}/human-review/reject",
    response_model=HumanReviewActionResponse,
    summary="驳回人工审核",
    description="驳回待人工审核会话并结束本次分析",
)
async def reject_human_review(session_id: str, body: HumanReviewRejectRequest):
    """驳回待人工审核的会话，并结束本次分析。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )
    rejected = await debate_service.reject_human_review(
        session_id,
        approver=body.approver,
        reason=body.reason,
    )
    if not rejected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no pending human review to reject",
        )
    await runtime_task_registry.mark_review_decision(
        session_id,
        review_status="rejected",
        status="failed",
        error="human_review_rejected",
    )
    await incident_service.update_incident(
        session.incident_id,
        IncidentUpdate(
            status=IncidentStatus.CLOSED,
            fix_suggestion=body.reason or "human_review_rejected",
        ),
    )
    return HumanReviewActionResponse(
        session_id=session_id,
        success=True,
        review_status="rejected",
        message="human review rejected",
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="查询异步辩论任务状态",
)
async def get_task_status(task_id: str):
    """查询异步辩论任务状态。"""
    try:
        task = task_queue.get(task_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return TaskResponse(
        task_id=task_id,
        status=task["status"],
        result=task.get("result"),
        error=task.get("error"),
    )


@router.get(
    "/",
    response_model=DebateListResponse,
    summary="获取辩论会话列表",
    description="分页获取辩论会话列表"
)
async def list_debates(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    incident_id: Optional[str] = Query(None, description="按故障ID筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
):
    """分页获取辩论会话列表。"""
    status_filter = DebateStatus(status) if status else None
    
    result = await debate_service.list_sessions(
        incident_id=incident_id,
        status=status_filter,
        page=page,
        page_size=page_size
    )
    
    items = [
        DebateSessionResponse(
            id=s.id,
            incident_id=s.incident_id,
            status=s.status.value,
            current_phase=s.current_phase.value if s.current_phase else None,
            current_round=s.current_round,
            created_at=s.created_at,
            updated_at=s.updated_at,
            completed_at=s.completed_at,
        )
        for s in result["items"]
    ]
    
    return DebateListResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get(
    "/{session_id}",
    response_model=DebateDetailResponse,
    summary="获取辩论会话详情",
    description="根据ID获取辩论会话详情"
)
async def get_debate(session_id: str):
    """读取单个辩论会话详情。"""
    session = await debate_service.get_session(session_id)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found"
        )
    
    rounds = [
        DebateRoundResponse(
            round_number=r.round_number,
            phase=r.phase.value,
            agent_name=r.agent_name,
            agent_role=r.agent_role,
            model=r.model,
            input_message=r.input_message,
            output_content=r.output_content,
            confidence=r.confidence,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in session.rounds
    ]
    
    return DebateDetailResponse(
        id=session.id,
        incident_id=session.incident_id,
        status=session.status.value,
        current_phase=session.current_phase.value if session.current_phase else None,
        current_round=session.current_round,
        created_at=session.created_at,
        updated_at=session.updated_at,
        completed_at=session.completed_at,
        rounds=rounds,
        context=session.context,
    )


@router.get(
    "/{session_id}/result",
    response_model=DebateResultResponse,
    summary="获取辩论结果",
    description="获取辩论会话的最终结果"
)
async def get_debate_result(session_id: str):
    """读取单个辩论会话的最终结果。"""
    result = await debate_service.get_result(session_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate result for session {session_id} not found"
        )
    
    return _build_result_response(result)


@router.get(
    "/{session_id}/lineage",
    response_model=LineageResponse,
    summary="获取会话执行谱系",
    description="返回 session 的事件/Agent/工具调用谱系记录",
)
async def get_session_lineage(
    session_id: str,
    limit: int = Query(200, ge=1, le=2000, description="最多返回记录数"),
):
    """读取指定 session 的谱系记录，并自动尝试 llm/runtime session 映射。"""
    resolved_session_id, rows = await _resolve_lineage_session_rows(session_id)
    subset = rows[: max(1, int(limit))]
    summary = await lineage_recorder.summarize(resolved_session_id)
    return LineageResponse(
        session_id=session_id,
        resolved_session_id=resolved_session_id,
        records=int(summary.get("records") or 0),
        events=int(summary.get("events") or 0),
        tools=int(summary.get("tools") or 0),
        agents=list(summary.get("agents") or []),
        first_ts=summary.get("first_ts"),
        last_ts=summary.get("last_ts"),
        items=[row.model_dump(mode="json") for row in subset],
    )


@router.get(
    "/{session_id}/replay",
    response_model=ReplayResponse,
    summary="回放会话关键流程",
    description="按时间线回放执行节点，用于失败会话快速复盘",
)
async def replay_session(
    session_id: str,
    limit: int = Query(120, ge=1, le=1000, description="回放步数上限"),
    phase: str = Query("", description="按阶段过滤（可选）"),
    agent: str = Query("", description="按 Agent 过滤（可选）"),
):
    """按时间线回放指定 session 的关键执行步骤。"""
    resolved_session_id, rows = await _resolve_lineage_session_rows(session_id)
    if rows:
        payload = await replay_session_lineage(resolved_session_id, limit=limit, phase=phase, agent=agent)
    else:
        payload = await replay_session_lineage(session_id, limit=limit, phase=phase, agent=agent)
    return ReplayResponse(
        session_id=session_id,
        resolved_session_id=resolved_session_id,
        count=int(payload.get("count") or 0),
        rendered_steps=list(payload.get("rendered_steps") or []),
        summary=dict(payload.get("summary") or {}),
        timeline=list(payload.get("timeline") or []),
        filters=dict(payload.get("filters") or {}),
        key_decisions=list(payload.get("key_decisions") or []),
        evidence_refs=[str(item) for item in (payload.get("evidence_refs") or [])],
    )


@router.get(
    "/output-refs/{ref_id}",
    response_model=OutputReferenceResponse,
    summary="获取截断输出完整内容",
    description="通过 ref_id 读取本地保存的完整输出",
)
async def get_output_ref(ref_id: str):
    """根据 ref_id 读取被截断输出的完整内容。"""
    payload = get_output_reference(ref_id)
    if not payload:
        return OutputReferenceResponse(ref_id=ref_id, found=False)
    return OutputReferenceResponse(
        ref_id=str(payload.get("ref_id") or ref_id),
        found=True,
        session_id=str(payload.get("session_id") or ""),
        category=str(payload.get("category") or ""),
        content=str(payload.get("content") or ""),
        metadata=dict(payload.get("metadata") or {}),
        created_at=str(payload.get("created_at") or ""),
    )


async def _resolve_lineage_session_rows(session_id: str) -> tuple[str, List[Any]]:
    """为谱系查询解析真实写盘的 session 标识。

    有些轨迹会写到 llm_session_id 或 runtime_session_id，下游查询时需要自动回查。"""
    session_key = str(session_id or "").strip()
    if not session_key:
        return "unknown", []

    direct_rows = await lineage_recorder.read(session_key)
    if direct_rows:
        return session_key, direct_rows

    debate_session = await debate_service.get_session(session_key)
    if not debate_session:
        return session_key, []

    candidates: List[str] = []
    llm_session_id = str(getattr(debate_session, "llm_session_id", "") or "").strip()
    if llm_session_id and llm_session_id != session_key:
        candidates.append(llm_session_id)
    runtime_session_id = str((debate_session.context or {}).get("runtime_session_id") or "").strip()
    if runtime_session_id and runtime_session_id not in {session_key, *candidates}:
        candidates.append(runtime_session_id)

    for candidate in candidates:
        rows = await lineage_recorder.read(candidate)
        if rows:
            return candidate, rows
    return session_key, []


def _build_result_response(result: DebateResult) -> DebateResultResponse:
    """把服务层 `DebateResult` 对象转换为标准 API 响应结构。"""
    evidence_chain = [
        EvidenceItemResponse(
            type=e.type,
            description=e.description,
            source=e.source,
            location=e.location,
            strength=e.strength,
        )
        for e in result.evidence_chain
    ]
    
    fix_rec = None
    if result.fix_recommendation:
        fix_rec = FixRecommendationResponse(
            summary=result.fix_recommendation.summary,
            steps=result.fix_recommendation.steps,
            code_changes_required=result.fix_recommendation.code_changes_required,
            rollback_recommended=result.fix_recommendation.rollback_recommended,
            testing_requirements=result.fix_recommendation.testing_requirements,
        )
    
    impact = None
    if result.impact_analysis:
        impact = ImpactAnalysisResponse(
            affected_services=result.impact_analysis.affected_services,
            affected_users=result.impact_analysis.affected_users,
            business_impact=result.impact_analysis.business_impact,
            estimated_recovery_time=result.impact_analysis.estimated_recovery_time,
        )
    
    risk = None
    if result.risk_assessment:
        risk = RiskAssessmentResponse(
            risk_level=result.risk_assessment.risk_level,
            risk_factors=result.risk_assessment.risk_factors,
            mitigation_suggestions=result.risk_assessment.mitigation_suggestions,
        )
    
    return DebateResultResponse(
        session_id=result.session_id,
        incident_id=result.incident_id,
        root_cause=result.root_cause,
        root_cause_category=result.root_cause_category,
        confidence=result.confidence,
        root_cause_candidates=[
            RootCauseCandidateResponse(
                rank=item.rank,
                summary=item.summary,
                source_agent=item.source_agent,
                confidence=item.confidence,
                confidence_interval=list(item.confidence_interval or []),
                evidence_refs=list(item.evidence_refs or []),
            )
            for item in (result.root_cause_candidates or [])
        ],
        evidence_chain=evidence_chain,
        fix_recommendation=fix_rec,
        impact_analysis=impact,
        risk_assessment=risk,
        responsible_team=result.responsible_team,
        responsible_owner=result.responsible_owner,
        action_items=result.action_items,
        dissenting_opinions=result.dissenting_opinions,
        created_at=result.created_at,
    )
