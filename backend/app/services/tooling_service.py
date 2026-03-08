"""
工具配置服务模块

本模块提供工具配置的读写功能。

核心功能：
1. 读取当前生效的工具配置
2. 更新工具配置
3. 自动维护更新时间

配置内容：
- 外部数据源配置（日志、监控、CMDB 等）
- 工具启用/禁用状态
- API 端点和认证信息

使用场景：
- 前端配置页面管理工具
- Agent 调用工具时读取配置
- 动态调整工具行为

Tooling Service
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.config import settings
from app.models.tooling import AgentToolingConfig
from app.repositories.tooling_repository import (
    FileToolingRepository,
    InMemoryToolingRepository,
    ToolingRepository,
)


class ToolingService:
    """
    工具配置读写服务

    提供工具配置的读取和更新功能。

    属性：
    - _repository: 配置存储仓储

    工作流程：
    1. 前端发起配置更新请求
    2. 自动更新 updated_at 字段
    3. 持久化到存储
    """

    def __init__(self, repository: Optional[ToolingRepository] = None):
        """
        初始化工具配置服务

        根据配置选择存储后端。

        Args:
            repository: 配置仓储，未提供则根据配置选择
        """
        self._repository = repository or (
            FileToolingRepository()
            if settings.LOCAL_STORE_BACKEND == "file"
            else InMemoryToolingRepository()
        )

    async def get_config(self) -> AgentToolingConfig:
        """
        获取当前工具配置

        Returns:
            AgentToolingConfig: 当前生效的工具配置
        """
        return await self._repository.get()

    async def update_config(self, config: AgentToolingConfig) -> AgentToolingConfig:
        """
        更新工具配置

        自动刷新更新时间。

        Args:
            config: 新的工具配置

        Returns:
            AgentToolingConfig: 更新后的配置
        """
        next_config = config.model_copy(update={"updated_at": datetime.utcnow()})
        return await self._repository.save(next_config)


# 全局实例
tooling_service = ToolingService()