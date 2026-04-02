"""页面自动巡检模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MonitorTargetCreate(BaseModel):
    """创建巡检目标请求。"""

    name: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=5, max_length=1024)
    enabled: bool = True
    check_interval_sec: int = Field(default=60, ge=15, le=3600)
    timeout_sec: int = Field(default=20, ge=5, le=120)
    cooldown_sec: int = Field(default=300, ge=30, le=7200)
    service_name: str = Field(default="", max_length=120)
    environment: str = Field(default="prod", max_length=64)
    severity: str = Field(default="high", pattern="^(critical|high|medium|low)$")
    cookie_header: str = Field(default="", max_length=8192)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MonitorTargetUpdate(BaseModel):
    """更新巡检目标请求。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    url: Optional[str] = Field(default=None, min_length=5, max_length=1024)
    enabled: Optional[bool] = None
    check_interval_sec: Optional[int] = Field(default=None, ge=15, le=3600)
    timeout_sec: Optional[int] = Field(default=None, ge=5, le=120)
    cooldown_sec: Optional[int] = Field(default=None, ge=30, le=7200)
    service_name: Optional[str] = Field(default=None, max_length=120)
    environment: Optional[str] = Field(default=None, max_length=64)
    severity: Optional[str] = Field(default=None, pattern="^(critical|high|medium|low)$")
    cookie_header: Optional[str] = Field(default=None, max_length=8192)
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class MonitorTarget(BaseModel):
    """巡检目标实体。"""

    id: str
    name: str
    url: str
    enabled: bool = True
    check_interval_sec: int = 60
    timeout_sec: int = 20
    cooldown_sec: int = 300
    service_name: str = ""
    environment: str = "prod"
    severity: str = "high"
    cookie_header: str = ""
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_checked_at: Optional[datetime] = None
    last_triggered_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PageMonitorFinding(BaseModel):
    """单次巡检结果。"""

    target_id: str
    target_name: str
    url: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    has_error: bool = False
    frontend_errors: List[str] = Field(default_factory=list)
    api_errors: List[str] = Field(default_factory=list)
    browser_error: str = ""
    summary: str = ""
    raw: Dict[str, Any] = Field(default_factory=dict)


class MonitorStatus(BaseModel):
    """巡检服务状态。"""

    running: bool
    tick_seconds: int
    active_targets: int
    last_loop_at: Optional[datetime] = None
