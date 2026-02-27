"""
Tooling settings APIs.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.tooling import AgentToolingConfig
from app.services.tooling_service import tooling_service

router = APIRouter()


@router.get(
    "/tooling",
    response_model=AgentToolingConfig,
    summary="获取 Agent 工具配置",
)
async def get_tooling_config():
    return await tooling_service.get_config()


@router.put(
    "/tooling",
    response_model=AgentToolingConfig,
    summary="更新 Agent 工具配置",
)
async def update_tooling_config(payload: AgentToolingConfig):
    return await tooling_service.update_config(payload)

