"""
故障事件服务
Incident Service
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.models.incident import (
    Incident,
    IncidentCreate,
    IncidentUpdate,
    IncidentList,
    IncidentStatus,
    IncidentSeverity,
)
from app.tools.log_parser import LogParserTool
from app.repositories.incident_repository import (
    IncidentRepository,
    InMemoryIncidentRepository,
)

logger = structlog.get_logger()


class IncidentService:
    """故障事件服务"""
    
    def __init__(self, repository: Optional[IncidentRepository] = None):
        self._repository = repository or InMemoryIncidentRepository()
        self._log_parser = LogParserTool()
    
    async def create_incident(self, data: IncidentCreate) -> Incident:
        """
        创建故障事件
        
        Args:
            data: 故障创建数据
            
        Returns:
            创建的故障事件
        """
        incident_id = f"inc_{uuid.uuid4().hex[:8]}"
        
        incident = Incident(
            id=incident_id,
            title=data.title,
            description=data.description,
            status=IncidentStatus.PENDING,
            severity=data.severity,
            source=data.source,
            log_content=data.log_content,
            exception_stack=data.exception_stack,
            trace_id=data.trace_id,
            service_name=data.service_name,
            environment=data.environment,
            metadata=data.metadata,
        )
        
        # 如果有日志内容，进行解析
        if data.log_content:
            try:
                parsed = await self._log_parser.execute(log_content=data.log_content)
                if parsed.success:
                    incident.parsed_data = parsed.data
                    # 自动推断严重程度
                    if not data.severity:
                        incident.severity = self._infer_severity(parsed.data or {})
            except Exception as e:
                logger.warning("log_parse_failed", error=str(e))
        
        await self._repository.create(incident)
        
        logger.info(
            "incident_created",
            incident_id=incident_id,
            title=data.title,
            source=data.source
        )
        
        return incident
    
    async def get_incident(self, incident_id: str) -> Optional[Incident]:
        """
        获取故障事件
        
        Args:
            incident_id: 故障ID
            
        Returns:
            故障事件或 None
        """
        return await self._repository.get(incident_id)
    
    async def update_incident(
        self,
        incident_id: str,
        data: IncidentUpdate
    ) -> Optional[Incident]:
        """
        更新故障事件
        
        Args:
            incident_id: 故障ID
            data: 更新数据
            
        Returns:
            更新后的故障事件或 None
        """
        incident = await self._repository.get(incident_id)
        if not incident:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        
        for key, value in update_data.items():
            setattr(incident, key, value)
        
        incident.updated_at = datetime.utcnow()
        
        # 如果状态变为已解决，记录解决时间
        if data.status == IncidentStatus.RESOLVED and not incident.resolved_at:
            incident.resolved_at = datetime.utcnow()
        
        logger.info(
            "incident_updated",
            incident_id=incident_id,
            updates=list(update_data.keys())
        )
        
        await self._repository.update(incident)
        return incident
    
    async def list_incidents(
        self,
        status: Optional[IncidentStatus] = None,
        severity: Optional[IncidentSeverity] = None,
        service_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> IncidentList:
        """
        列出故障事件
        
        Args:
            status: 状态过滤
            severity: 严重程度过滤
            service_name: 服务名称过滤
            page: 页码
            page_size: 每页数量
            
        Returns:
            故障列表
        """
        incidents = await self._repository.list_all()
        
        # 过滤
        if status:
            incidents = [i for i in incidents if i.status == status]
        if severity:
            incidents = [i for i in incidents if i.severity == severity]
        if service_name:
            incidents = [i for i in incidents if i.service_name == service_name]
        
        # 排序（按创建时间倒序）
        incidents.sort(key=lambda x: x.created_at, reverse=True)
        
        # 分页
        total = len(incidents)
        start = (page - 1) * page_size
        end = start + page_size
        items = incidents[start:end]
        
        return IncidentList(
            items=items,
            total=total,
            page=page,
            page_size=page_size
        )
    
    async def delete_incident(self, incident_id: str) -> bool:
        """
        删除故障事件
        
        Args:
            incident_id: 故障ID
            
        Returns:
            是否成功
        """
        deleted = await self._repository.delete(incident_id)
        if deleted:
            logger.info("incident_deleted", incident_id=incident_id)
        return deleted
    
    def _infer_severity(self, parsed_data: Dict[str, Any]) -> IncidentSeverity:
        """
        根据解析数据推断严重程度
        
        Args:
            parsed_data: 解析后的日志数据
            
        Returns:
            推断的严重程度
        """
        # 检查异常类型
        exceptions = parsed_data.get("exceptions", [])
        if exceptions:
            exception_type = exceptions[0].get("type", "")
            if exception_type in ["OutOfMemoryError", "StackOverflowError"]:
                return IncidentSeverity.CRITICAL
        
        # 检查日志级别
        log_lines = parsed_data.get("log_lines", [])
        if log_lines:
            level = log_lines[0].get("level", "").upper()
            if level == "FATAL":
                return IncidentSeverity.CRITICAL
            if level == "ERROR":
                return IncidentSeverity.HIGH
            if level == "WARN":
                return IncidentSeverity.MEDIUM
        
        return IncidentSeverity.LOW


# 全局实例
incident_service = IncidentService()
