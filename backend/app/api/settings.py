"""
Tooling settings APIs.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.tooling import AgentToolingConfig
from app.services.tooling_service import tooling_service
from app.runtime.tool_registry import tool_registry_service
from app.runtime.trace_lineage import lineage_recorder

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


@router.get(
    "/tooling/registry",
    summary="获取工具注册中心",
)
async def get_tool_registry():
    return await tool_registry_service.list_items()


@router.get(
    "/tooling/connectors",
    summary="获取连接器协议清单",
)
async def get_tool_connectors():
    return await tool_registry_service.connectors()


@router.get(
    "/tooling/audit/{session_id}",
    summary="获取工具调用审计记录",
)
async def get_tool_audit(session_id: str, limit: int = 200):
    rows = await lineage_recorder.read(session_id)
    tools = [row.model_dump(mode="json") for row in rows if row.kind == "tool"]
    return {
        "session_id": session_id,
        "count": len(tools),
        "items": tools[: max(1, int(limit or 200))],
    }
