"""
故障事件模型
Incident Models
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IncidentStatus(str, Enum):
    """故障状态"""
    PENDING = "pending"          # 待处理
    ANALYZING = "analyzing"      # 分析中
    DEBATING = "debating"        # 辩论中
    RESOLVED = "resolved"        # 已解决
    CLOSED = "closed"            # 已关闭


class IncidentSeverity(str, Enum):
    """故障严重程度"""
    CRITICAL = "critical"        # 严重 - 影响核心业务
    HIGH = "high"               # 高 - 影响重要功能
    MEDIUM = "medium"           # 中 - 影响一般功能
    LOW = "low"                 # 低 - 影响较小


class IncidentSource(str, Enum):
    """故障来源"""
    LOG = "log"                 # 日志
    MONITOR = "monitor"         # 监控告警
    USER_REPORT = "user_report" # 用户反馈
    MANUAL = "manual"           # 手动创建


class IncidentCreate(BaseModel):
    """创建故障请求"""
    title: str = Field(..., description="故障标题")
    description: Optional[str] = Field(None, description="故障描述")
    source: IncidentSource = Field(default=IncidentSource.MANUAL, description="故障来源")
    severity: Optional[IncidentSeverity] = Field(None, description="严重程度")
    
    # 运行态数据
    log_content: Optional[str] = Field(None, description="日志内容")
    exception_stack: Optional[str] = Field(None, description="异常堆栈")
    trace_id: Optional[str] = Field(None, description="链路追踪ID")
    
    # 上下文信息
    service_name: Optional[str] = Field(None, description="服务名称")
    environment: Optional[str] = Field(None, description="环境")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")


class IncidentUpdate(BaseModel):
    """更新故障请求"""
    title: Optional[str] = Field(None, description="故障标题")
    description: Optional[str] = Field(None, description="故障描述")
    status: Optional[IncidentStatus] = Field(None, description="状态")
    severity: Optional[IncidentSeverity] = Field(None, description="严重程度")
    root_cause: Optional[str] = Field(None, description="根因")
    fix_suggestion: Optional[str] = Field(None, description="修复建议")
    impact_analysis: Optional[Dict[str, Any]] = Field(None, description="影响分析")
    debate_session_id: Optional[str] = Field(None, description="辩论会话ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class Incident(BaseModel):
    """故障事件"""
    id: str = Field(..., description="故障ID")
    title: str = Field(..., description="故障标题")
    description: Optional[str] = Field(None, description="故障描述")
    status: IncidentStatus = Field(default=IncidentStatus.PENDING, description="状态")
    severity: Optional[IncidentSeverity] = Field(None, description="严重程度")
    source: IncidentSource = Field(default=IncidentSource.MANUAL, description="来源")
    
    # 运行态数据
    log_content: Optional[str] = Field(None, description="日志内容")
    exception_stack: Optional[str] = Field(None, description="异常堆栈")
    trace_id: Optional[str] = Field(None, description="链路追踪ID")
    
    # 解析后的结构化数据
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="解析后的数据")
    
    # 上下文信息
    service_name: Optional[str] = Field(None, description="服务名称")
    environment: Optional[str] = Field(None, description="环境")
    
    # 分析结果
    root_cause: Optional[str] = Field(None, description="根因")
    fix_suggestion: Optional[str] = Field(None, description="修复建议")
    impact_analysis: Optional[Dict[str, Any]] = Field(None, description="影响分析")
    
    # 关联信息
    debate_session_id: Optional[str] = Field(None, description="辩论会话ID")
    related_incidents: List[str] = Field(default_factory=list, description="关联故障")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    resolved_at: Optional[datetime] = Field(None, description="解决时间")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "inc_001",
                "title": "订单服务 NullPointerException",
                "description": "创建订单时发生空指针异常",
                "status": "analyzing",
                "severity": "high",
                "source": "log",
                "log_content": "2024-01-15 10:30:00 ERROR [OrderService] NullPointerException...",
                "exception_stack": "java.lang.NullPointerException\n\tat com.example.OrderService.createOrder...",
                "service_name": "order-service",
                "environment": "production"
            }
        }


class IncidentList(BaseModel):
    """故障列表"""
    items: List[Incident]
    total: int
    page: int
    page_size: int
