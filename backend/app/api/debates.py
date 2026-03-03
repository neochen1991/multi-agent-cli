"""
辩论 API
Debate API Endpoints
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
from app.services.debate_service import debate_service
from app.services.incident_service import incident_service
from app.core.task_queue import task_queue
from app.config import settings
from app.runtime.trace_lineage import lineage_recorder, replay_session_lineage

router = APIRouter()


# ==================== API 数据模型 ====================

class DebateSessionResponse(BaseModel):
    """辩论会话响应"""
    id: str
    incident_id: str
    status: str
    current_phase: Optional[str]
    current_round: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DebateRoundResponse(BaseModel):
    """辩论轮次响应"""
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
    """证据项响应"""
    type: str
    description: str
    source: str
    location: Optional[str]
    strength: str


class RootCauseCandidateResponse(BaseModel):
    rank: int
    summary: str
    source_agent: Optional[str] = None
    confidence: float
    confidence_interval: List[float] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)


class FixRecommendationResponse(BaseModel):
    """修复建议响应"""
    summary: str
    steps: List[Dict[str, Any]]
    code_changes_required: bool
    rollback_recommended: bool
    testing_requirements: List[str]


class ImpactAnalysisResponse(BaseModel):
    """影响分析响应"""
    affected_services: List[str]
    affected_users: Optional[str]
    business_impact: Optional[str]
    estimated_recovery_time: Optional[str]


class RiskAssessmentResponse(BaseModel):
    """风险评估响应"""
    risk_level: str
    risk_factors: List[str]
    mitigation_suggestions: List[str]


class DebateResultResponse(BaseModel):
    """辩论结果响应"""
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
    """辩论详情响应"""
    rounds: List[DebateRoundResponse]
    context: Dict[str, Any]


class DebateListResponse(BaseModel):
    """辩论列表响应"""
    items: List[DebateSessionResponse]
    total: int
    page: int
    page_size: int


class TaskResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CancelResponse(BaseModel):
    session_id: str
    cancelled: bool


class LineageResponse(BaseModel):
    session_id: str
    records: int
    events: int
    tools: int
    agents: List[str]
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


class ReplayResponse(BaseModel):
    session_id: str
    count: int
    rendered_steps: List[str]
    summary: Dict[str, Any]
    timeline: List[Dict[str, Any]]
    key_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)


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
):
    """创建辩论会话"""
    # 获取故障事件
    incident = await incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    # 创建辩论会话
    session = await debate_service.create_session(
        incident,
        max_rounds=max_rounds,
    )
    
    # 更新故障状态
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
    """执行辩论流程"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found"
        )
    
    if session.status == DebateStatus.COMPLETED:
        # 已完成，返回已有结果
        result = await debate_service.get_result(session_id)
        if result:
            return _build_result_response(result)
    
    try:
        result = await debate_service.execute_debate(
            session_id,
            retry_failed_only=retry_failed_only,
        )
        
        # 更新故障状态和结果
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
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )

    async def _run():
        try:
            result = await asyncio.wait_for(
                debate_service.execute_debate(
                    session_id,
                    retry_failed_only=retry_failed_only,
                ),
                timeout=max(60, int(settings.DEBATE_TIMEOUT or 600)),
            )
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
        except Exception as exc:
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
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )
    cancelled = await debate_service.cancel_session(session_id, reason="api_cancel")
    return CancelResponse(session_id=session_id, cancelled=cancelled)


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="查询异步辩论任务状态",
)
async def get_task_status(task_id: str):
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
    """获取辩论会话列表"""
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
    """获取辩论会话详情"""
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
    """获取辩论结果"""
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
    rows = await lineage_recorder.read(session_id)
    subset = rows[: max(1, int(limit))]
    summary = await lineage_recorder.summarize(session_id)
    return LineageResponse(
        session_id=session_id,
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
):
    payload = await replay_session_lineage(session_id, limit=limit)
    return ReplayResponse(
        session_id=payload["session_id"],
        count=int(payload.get("count") or 0),
        rendered_steps=list(payload.get("rendered_steps") or []),
        summary=dict(payload.get("summary") or {}),
        timeline=list(payload.get("timeline") or []),
        key_decisions=list(payload.get("key_decisions") or []),
        evidence_refs=[str(item) for item in (payload.get("evidence_refs") or [])],
    )


def _build_result_response(result: DebateResult) -> DebateResultResponse:
    """构建辩论结果响应"""
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
