"""
Tooling settings APIs.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.tooling import AgentToolingConfig
from app.services.tooling_service import tooling_service
from app.runtime.tool_registry import tool_registry_service
from app.runtime.trace_lineage import lineage_recorder
from app.services.agent_tool_context_service import agent_tool_context_service
from app.services.debate_service import debate_service

router = APIRouter()


TOOL_AGENT_MAP: Dict[str, str] = {
    "git_repo_search": "CodeAgent",
    "git_change_window": "ChangeAgent",
    "local_log_reader": "LogAgent",
    "domain_excel_lookup": "DomainAgent",
    "db_snapshot_reader": "DatabaseAgent",
    "metrics_snapshot_analyzer": "MetricsAgent",
    "grafana_connector": "MetricsAgent",
    "apm_connector": "MetricsAgent",
    "logcloud_connector": "LogAgent",
    "alert_platform_connector": "ProblemAnalysisAgent",
    "runbook_case_library": "RunbookAgent",
    "rule_suggestion_toolkit": "RuleSuggestionAgent",
}


class ToolTrialRunRequest(BaseModel):
    tool_name: str = Field(..., description="工具名")
    use_tool: Optional[bool] = Field(default=True, description="是否允许调用工具")
    task: str = Field(default="", description="主Agent下发任务")
    focus: str = Field(default="", description="关注点")
    expected_output: str = Field(default="", description="期望输出")
    compact_context: Dict[str, Any] = Field(default_factory=dict, description="轻量上下文")
    incident_context: Dict[str, Any] = Field(default_factory=dict, description="故障上下文")


class ToolRegistryUpsertRequest(BaseModel):
    tool_name: str = Field(..., description="工具名")
    category: str = Field(default="custom", description="工具分类")
    owner_agent: str = Field(default="CustomAgent", description="归属 Agent")
    enabled: bool = Field(default=True, description="是否启用")
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="输入参数 schema")
    policy: Dict[str, Any] = Field(default_factory=dict, description="策略配置")


class ToolRunRequest(BaseModel):
    input: Dict[str, Any] = Field(default_factory=dict, description="工具运行参数")


class ConnectorCallToolRequest(BaseModel):
    input: Dict[str, Any] = Field(default_factory=dict, description="连接器透传给工具的参数")


def _agent_for_tool(tool_name: str) -> str:
    agent_name = TOOL_AGENT_MAP.get(tool_name)
    if not agent_name:
        raise HTTPException(status_code=400, detail=f"不支持试跑该工具: {tool_name}")
    return agent_name


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


@router.post(
    "/tooling/registry",
    summary="创建工具注册项",
)
async def create_tool_registry_item(payload: ToolRegistryUpsertRequest):
    try:
        return await tool_registry_service.create_item(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/tooling/registry/{tool_name}",
    summary="获取工具注册详情",
)
async def get_tool_registry_item(tool_name: str):
    try:
        return await tool_registry_service.get_item(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.put(
    "/tooling/registry/{tool_name}",
    summary="更新工具注册项",
)
async def update_tool_registry_item(tool_name: str, payload: ToolRegistryUpsertRequest):
    try:
        body = payload.model_dump(mode="json")
        body["tool_name"] = tool_name
        return await tool_registry_service.update_item(tool_name, body)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.delete(
    "/tooling/registry/{tool_name}",
    summary="删除工具注册项",
)
async def delete_tool_registry_item(tool_name: str):
    return await tool_registry_service.delete_item(tool_name)


@router.post(
    "/tooling/registry/{tool_name}/start",
    summary="启动工具",
)
async def start_tool_registry_item(tool_name: str):
    try:
        return await tool_registry_service.start(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.post(
    "/tooling/registry/{tool_name}/offline",
    summary="下线工具",
)
async def offline_tool_registry_item(tool_name: str):
    try:
        return await tool_registry_service.offline(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.get(
    "/tooling/registry/{tool_name}/health",
    summary="工具健康检查",
)
async def tool_registry_item_health(tool_name: str):
    try:
        return await tool_registry_service.health(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.post(
    "/tooling/registry/{tool_name}/run",
    summary="执行工具（服务入口）",
)
async def run_tool_registry_item(tool_name: str, payload: ToolRunRequest):
    try:
        return await tool_registry_service.run(tool_name, payload.input)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.get(
    "/tooling/connectors",
    summary="获取连接器协议清单",
)
async def get_tool_connectors():
    return await tool_registry_service.connectors()


@router.post(
    "/tooling/connectors/{connector_name}/connect",
    summary="连接连接器",
)
async def connect_tool_connector(connector_name: str):
    try:
        return await tool_registry_service.connect(connector_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"连接器不存在: {connector_name}")


@router.post(
    "/tooling/connectors/{connector_name}/disconnect",
    summary="断开连接器",
)
async def disconnect_tool_connector(connector_name: str):
    try:
        return await tool_registry_service.disconnect(connector_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"连接器不存在: {connector_name}")


@router.get(
    "/tooling/connectors/{connector_name}/tools",
    summary="查看连接器可用工具集",
)
async def list_connector_tools(connector_name: str):
    try:
        return await tool_registry_service.list_tools(connector_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"连接器不存在: {connector_name}")


@router.post(
    "/tooling/connectors/{connector_name}/call-tool/{tool_name}",
    summary="通过连接器调用工具",
)
async def call_connector_tool(
    connector_name: str,
    tool_name: str,
    payload: ConnectorCallToolRequest,
):
    try:
        return await tool_registry_service.call_tool(connector_name, tool_name, payload.input)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"连接器不存在: {connector_name}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/tooling/audit/{session_id}",
    summary="获取工具调用审计记录",
)
async def get_tool_audit(session_id: str, limit: int = 200):
    resolved_session_id = str(session_id or "").strip()
    rows = await lineage_recorder.read(resolved_session_id)
    if not rows:
        debate_session = await debate_service.get_session(resolved_session_id)
        if debate_session:
            llm_session_id = str(getattr(debate_session, "llm_session_id", "") or "").strip()
            if llm_session_id and llm_session_id != resolved_session_id:
                mapped_rows = await lineage_recorder.read(llm_session_id)
                if mapped_rows:
                    resolved_session_id = llm_session_id
                    rows = mapped_rows
            if not rows:
                runtime_session_id = str((debate_session.context or {}).get("runtime_session_id") or "").strip()
                if runtime_session_id and runtime_session_id != resolved_session_id:
                    mapped_rows = await lineage_recorder.read(runtime_session_id)
                    if mapped_rows:
                        resolved_session_id = runtime_session_id
                        rows = mapped_rows
    tools = [row.model_dump(mode="json") for row in rows if row.kind == "tool"]
    return {
        "session_id": session_id,
        "resolved_session_id": resolved_session_id,
        "count": len(tools),
        "items": tools[: max(1, int(limit or 200))],
    }


@router.post(
    "/tooling/trial-run",
    summary="工具参数试跑",
)
async def trial_run_tool(payload: ToolTrialRunRequest):
    tool_name = str(payload.tool_name or "").strip()
    agent_name = _agent_for_tool(tool_name)
    compact_context = dict(payload.compact_context or {})
    incident_context = dict(payload.incident_context or {})
    assigned_command = {
        "task": str(payload.task or "").strip() or f"请调用 {tool_name} 收集外部证据",
        "focus": str(payload.focus or "").strip() or tool_name,
        "expected_output": str(payload.expected_output or "").strip() or "返回工具输出与证据摘要",
        "use_tool": True if payload.use_tool is None else bool(payload.use_tool),
    }
    result = await agent_tool_context_service.build_context(
        agent_name=agent_name,
        compact_context=compact_context,
        incident_context=incident_context,
        assigned_command=assigned_command,
    )
    return {
        "tool_name": tool_name,
        "agent_name": agent_name,
        **result,
    }
