"""
故障事件服务模块

本模块提供故障事件的管理功能，包括：
1. 创建故障事件（含日志自动解析）
2. 获取/更新/删除故障事件
3. 列表查询（支持过滤和分页）
4. 严重程度自动推断

数据流：
用户提交故障 -> 解析日志 -> 推断严重程度 -> 存储故障 -> 返回 Incident

Incident Service
"""

import uuid
from datetime import UTC, datetime
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
    FileIncidentRepository,
)
from app.config import settings

logger = structlog.get_logger()


class IncidentService:
    """
    故障事件服务

    提供故障事件的完整生命周期管理：
    - 创建：自动解析日志，推断严重程度
    - 查询：支持状态、严重程度、服务名过滤
    - 更新：状态变更、根因记录
    - 删除：清理故障记录

    自动严重程度推断规则：
    - OutOfMemoryError/StackOverflowError -> CRITICAL
    - FATAL 日志级别 -> CRITICAL
    - ERROR 日志级别 -> HIGH
    - WARN 日志级别 -> MEDIUM
    - 其他 -> LOW
    """

    def __init__(self, repository: Optional[IncidentRepository] = None):
        """
        初始化故障服务

        Args:
            repository: 故障存储库，未提供则根据配置选择文件或内存存储
        """
        self._repository = repository or (
            FileIncidentRepository()
            if settings.LOCAL_STORE_BACKEND == "file"
            else InMemoryIncidentRepository()
        )
        self._log_parser = LogParserTool()

    @staticmethod
    def _created_at_sort_key(incident: Incident) -> datetime:
        """
        统一 incident.created_at 的排序口径。

        中文注释：历史本地文件里可能混有无时区时间；这里在排序入口统一补成 UTC，
        避免列表接口因为 naive/aware 混排直接崩掉。
        """
        created_at = incident.created_at
        if isinstance(created_at, datetime):
            if created_at.tzinfo is None:
                return created_at.replace(tzinfo=UTC)
            return created_at.astimezone(UTC)
        return datetime.min.replace(tzinfo=UTC)
    
    async def create_incident(self, data: IncidentCreate) -> Incident:
        """
        创建故障事件

        创建流程：
        1. 生成唯一故障 ID
        2. 构建 Incident 对象
        3. 如果有日志内容，自动解析并推断严重程度
        4. 持久化到存储库

        Args:
            data: 故障创建数据（标题、描述、日志等）

        Returns:
            Incident: 创建的故障事件
        """
        # 生成唯一故障 ID
        incident_id = f"inc_{uuid.uuid4().hex[:8]}"

        # 构建故障对象
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

        # 如果有日志内容，进行自动解析
        if data.log_content:
            try:
                parsed = await self._log_parser.execute(log_content=data.log_content)
                if parsed.success:
                    incident.parsed_data = parsed.data
                    # 自动推断严重程度（仅当用户未指定时）
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
            incident_id: 故障 ID

        Returns:
            Optional[Incident]: 故障事件，不存在则返回 None
        """
        return await self._repository.get(incident_id)

    async def update_incident(
        self,
        incident_id: str,
        data: IncidentUpdate
    ) -> Optional[Incident]:
        """
        更新故障事件

        更新流程：
        1. 获取现有故障
        2. 应用更新字段
        3. 如果状态变为已解决，记录解决时间
        4. 持久化更新

        Args:
            incident_id: 故障 ID
            data: 更新数据

        Returns:
            Optional[Incident]: 更新后的故障事件，不存在则返回 None
        """
        incident = await self._repository.get(incident_id)
        if not incident:
            return None

        # 应用更新字段
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

        支持多条件过滤和分页：
        - status: 按状态过滤
        - severity: 按严重程度过滤
        - service_name: 按服务名过滤
        - page/page_size: 分页参数

        结果按创建时间倒序排列。

        Args:
            status: 状态过滤
            severity: 严重程度过滤
            service_name: 服务名称过滤
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            IncidentList: 故障列表（含总数和分页信息）
        """
        incidents = await self._repository.list_all()

        # 应用过滤条件
        if status:
            incidents = [i for i in incidents if i.status == status]
        if severity:
            incidents = [i for i in incidents if i.severity == severity]
        if service_name:
            incidents = [i for i in incidents if i.service_name == service_name]

        # 按创建时间倒序排列
        incidents.sort(key=self._created_at_sort_key, reverse=True)

        # 分页处理
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
            incident_id: 故障 ID

        Returns:
            bool: 是否成功删除
        """
        deleted = await self._repository.delete(incident_id)
        if deleted:
            logger.info("incident_deleted", incident_id=incident_id)
        return deleted

    def _infer_severity(self, parsed_data: Dict[str, Any]) -> IncidentSeverity:
        """
        根据解析数据推断严重程度

        推断规则（按优先级）：
        1. 异常类型判断：
           - OutOfMemoryError, StackOverflowError -> CRITICAL
        2. 日志级别判断：
           - FATAL -> CRITICAL
           - ERROR -> HIGH
           - WARN -> MEDIUM
        3. 默认 -> LOW

        Args:
            parsed_data: 日志解析数据

        Returns:
            IncidentSeverity: 推断的严重程度
        """
        # 先检查异常类型
        exceptions = parsed_data.get("exceptions", [])
        if exceptions:
            exception_type = exceptions[0].get("type", "")
            if exception_type in ["OutOfMemoryError", "StackOverflowError"]:
                return IncidentSeverity.CRITICAL

        # 再检查日志级别
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
