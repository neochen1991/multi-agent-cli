"""
故障事件 API
Incident API Endpoints
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.incident import (
    Incident,
    IncidentCreate as IncidentCreateModel,
    IncidentUpdate,
    IncidentStatus,
    IncidentSeverity,
    IncidentList,
)
from app.services.incident_service import incident_service

router = APIRouter()


# ==================== API 数据模型 ====================

class ExceptionInfo(BaseModel):
    """异常信息"""
    type: str = Field(..., description="异常类型")
    message: str = Field(..., description="异常消息")
    stack_trace: List[str] = Field(default_factory=list, description="堆栈跟踪")
    cause: Optional[str] = Field(None, description="根本原因异常")


class SourceInfo(BaseModel):
    """来源信息"""
    service_name: str = Field(..., description="服务名称")
    instance_id: Optional[str] = Field(None, description="实例ID")
    environment: Optional[str] = Field(None, description="环境")


class RuntimeAssetCreate(BaseModel):
    """创建运行态资产"""
    exception: Optional[ExceptionInfo] = None
    raw_logs: List[str] = Field(default_factory=list, description="原始日志")
    source: SourceInfo = Field(..., description="来源信息")


class IncidentCreateRequest(BaseModel):
    """创建故障事件请求"""
    title: str = Field(..., min_length=1, max_length=255, description="故障标题")
    description: Optional[str] = Field(None, description="故障描述")
    severity: Optional[str] = Field(
        None,
        description="严重程度: critical/high/medium/low"
    )
    source: str = Field(default="manual", description="来源: log/monitor/user_report/manual")
    
    # 运行态数据
    log_content: Optional[str] = Field(None, description="日志内容")
    exception_stack: Optional[str] = Field(None, description="异常堆栈")
    trace_id: Optional[str] = Field(None, description="链路追踪ID")
    
    # 上下文
    service_name: Optional[str] = Field(None, description="服务名称")
    environment: Optional[str] = Field(None, description="环境")


class IncidentResponse(BaseModel):
    """故障事件响应"""
    id: str
    title: str
    description: Optional[str]
    severity: Optional[str]
    status: str
    source: str
    service_name: Optional[str]
    root_cause: Optional[str]
    fix_suggestion: Optional[str]
    debate_session_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IncidentListResponse(BaseModel):
    """故障事件列表响应"""
    items: List[IncidentResponse]
    total: int
    page: int
    page_size: int


class IncidentDetailResponse(IncidentResponse):
    """故障事件详情响应"""
    log_content: Optional[str] = None
    exception_stack: Optional[str] = None
    parsed_data: Optional[dict] = None
    impact_analysis: Optional[dict] = None
    related_incidents: List[str] = []
    metadata: dict = {}


# ==================== API 端点 ====================

@router.post(
    "/",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建故障事件",
    description="创建新的故障事件，并触发分析流程"
)
async def create_incident(request: IncidentCreateRequest):
    """创建故障事件"""
    # 转换请求模型
    create_data = IncidentCreateModel(
        title=request.title,
        description=request.description,
        source=request.source,
        severity=IncidentSeverity(request.severity) if request.severity else None,
        log_content=request.log_content,
        exception_stack=request.exception_stack,
        trace_id=request.trace_id,
        service_name=request.service_name,
        environment=request.environment,
    )
    
    incident = await incident_service.create_incident(create_data)
    
    return IncidentResponse(
        id=incident.id,
        title=incident.title,
        description=incident.description,
        severity=incident.severity.value if incident.severity else None,
        status=incident.status.value,
        source=incident.source.value,
        service_name=incident.service_name,
        root_cause=incident.root_cause,
        fix_suggestion=incident.fix_suggestion,
        debate_session_id=incident.debate_session_id,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        resolved_at=incident.resolved_at,
    )


@router.get(
    "/",
    response_model=IncidentListResponse,
    summary="获取故障事件列表",
    description="分页获取故障事件列表"
)
async def list_incidents(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    severity: Optional[str] = Query(None, description="按严重程度筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    service_name: Optional[str] = Query(None, description="按服务名称筛选"),
):
    """获取故障事件列表"""
    status_filter = IncidentStatus(status) if status else None
    severity_filter = IncidentSeverity(severity) if severity else None
    
    result = await incident_service.list_incidents(
        status=status_filter,
        severity=severity_filter,
        service_name=service_name,
        page=page,
        page_size=page_size
    )
    
    items = [
        IncidentResponse(
            id=i.id,
            title=i.title,
            description=i.description,
            severity=i.severity.value if i.severity else None,
            status=i.status.value,
            source=i.source.value,
            service_name=i.service_name,
            root_cause=i.root_cause,
            fix_suggestion=i.fix_suggestion,
            debate_session_id=i.debate_session_id,
            created_at=i.created_at,
            updated_at=i.updated_at,
            resolved_at=i.resolved_at,
        )
        for i in result.items
    ]
    
    return IncidentListResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/{incident_id}",
    response_model=IncidentDetailResponse,
    summary="获取故障事件详情",
    description="根据ID获取故障事件详情"
)
async def get_incident(incident_id: str):
    """获取故障事件详情"""
    incident = await incident_service.get_incident(incident_id)
    
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    return IncidentDetailResponse(
        id=incident.id,
        title=incident.title,
        description=incident.description,
        severity=incident.severity.value if incident.severity else None,
        status=incident.status.value,
        source=incident.source.value,
        service_name=incident.service_name,
        root_cause=incident.root_cause,
        fix_suggestion=incident.fix_suggestion,
        debate_session_id=incident.debate_session_id,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        resolved_at=incident.resolved_at,
        log_content=incident.log_content,
        exception_stack=incident.exception_stack,
        parsed_data=incident.parsed_data,
        impact_analysis=incident.impact_analysis,
        related_incidents=incident.related_incidents,
        metadata=incident.metadata,
    )


@router.put(
    "/{incident_id}",
    response_model=IncidentResponse,
    summary="更新故障事件",
    description="更新故障事件信息"
)
async def update_incident(
    incident_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
):
    """更新故障事件"""
    update_data = IncidentUpdate(
        title=title,
        description=description,
        severity=IncidentSeverity(severity) if severity else None,
        status=IncidentStatus(status) if status else None,
    )
    
    incident = await incident_service.update_incident(incident_id, update_data)
    
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    return IncidentResponse(
        id=incident.id,
        title=incident.title,
        description=incident.description,
        severity=incident.severity.value if incident.severity else None,
        status=incident.status.value,
        source=incident.source.value,
        service_name=incident.service_name,
        root_cause=incident.root_cause,
        fix_suggestion=incident.fix_suggestion,
        debate_session_id=incident.debate_session_id,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        resolved_at=incident.resolved_at,
    )


@router.delete(
    "/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除故障事件",
    description="删除指定的故障事件"
)
async def delete_incident(incident_id: str):
    """删除故障事件"""
    success = await incident_service.delete_incident(incident_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
