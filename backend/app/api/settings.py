"""工具配置与审计 API。

覆盖 Agent 工具配置读取、工具注册中心维护、连接器操作、工具审计查询和试跑入口。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models.tooling import AgentMCPBindingConfig, AgentToolingConfig, MCPServerConfig
from app.services.tooling_service import tooling_service
from app.services.mcp_service import mcp_service
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
    "agent_skill_router": "ProblemAnalysisAgent",
    "metrics_snapshot_analyzer": "MetricsAgent",
    "grafana_connector": "MetricsAgent",
    "apm_connector": "MetricsAgent",
    "logcloud_connector": "LogAgent",
    "alert_platform_connector": "ProblemAnalysisAgent",
    "runbook_case_library": "RunbookAgent",
    "rule_suggestion_toolkit": "RuleSuggestionAgent",
}


class ToolTrialRunRequest(BaseModel):
    """工具试跑请求，用于在不进入完整辩论链路的情况下验证工具上下文和入参。"""

    tool_name: str = Field(..., description="工具名")
    use_tool: Optional[bool] = Field(default=True, description="是否允许调用工具")
    task: str = Field(default="", description="主Agent下发任务")
    focus: str = Field(default="", description="关注点")
    expected_output: str = Field(default="", description="期望输出")
    compact_context: Dict[str, Any] = Field(default_factory=dict, description="轻量上下文")
    incident_context: Dict[str, Any] = Field(default_factory=dict, description="故障上下文")


class ToolRegistryUpsertRequest(BaseModel):
    """工具注册中心新增/更新请求。"""

    tool_name: str = Field(..., description="工具名")
    category: str = Field(default="custom", description="工具分类")
    owner_agent: str = Field(default="CustomAgent", description="归属 Agent")
    enabled: bool = Field(default=True, description="是否启用")
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="输入参数 schema")
    policy: Dict[str, Any] = Field(default_factory=dict, description="策略配置")


class ToolRunRequest(BaseModel):
    """工具服务直接运行时的透传入参。"""

    input: Dict[str, Any] = Field(default_factory=dict, description="工具运行参数")


class ConnectorCallToolRequest(BaseModel):
    """通过连接器转发工具调用时的参数载荷。"""

    input: Dict[str, Any] = Field(default_factory=dict, description="连接器透传给工具的参数")


class MCPServerUpsertRequest(BaseModel):
    """MCP 服务创建/更新请求。"""

    id: str = Field(default="", description="服务 ID，留空时自动生成")
    name: str = Field(..., min_length=1, description="服务名称")
    enabled: bool = Field(default=True, description="是否启用")
    type: str = Field(default="remote", description="服务类型：remote/local")
    transport: str = Field(default="http", description="传输协议：http/sse/stdio")
    protocol_mode: str = Field(default="gateway", description="调用模式：gateway/mcp/local")
    endpoint: str = Field(default="", description="服务地址（http/sse）")
    command: str = Field(default="", description="stdio 命令")
    command_list: list[str] = Field(default_factory=list, description="stdio 命令数组（兼容 OpenCode 风格）")
    args: list[str] = Field(default_factory=list, description="stdio 参数")
    env: Dict[str, str] = Field(default_factory=dict, description="stdio 环境变量")
    api_token: str = Field(default="", description="访问令牌")
    timeout_seconds: int = Field(default=12, ge=2, le=120, description="请求超时")
    capabilities: list[str] = Field(default_factory=lambda: ["logs", "metrics"], description="能力列表")
    tool_paths: Dict[str, str] = Field(default_factory=dict, description="能力路径映射")
    metadata: Dict[str, str] = Field(default_factory=dict, description="扩展元数据")


def _agent_for_tool(tool_name: str) -> str:
    """根据工具名映射默认归属 Agent，用于试跑时构造正确的上下文。"""
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
    """读取当前生效的 Agent 工具配置。"""
    return await tooling_service.get_config()


@router.put(
    "/tooling",
    response_model=AgentToolingConfig,
    summary="更新 Agent 工具配置",
)
async def update_tooling_config(payload: AgentToolingConfig):
    """更新全局 Agent 工具配置。"""
    return await tooling_service.update_config(payload)


@router.get(
    "/tooling/registry",
    summary="获取工具注册中心",
)
async def get_tool_registry():
    """列出工具注册中心中的全部工具项。"""
    return await tool_registry_service.list_items()


@router.post(
    "/tooling/registry",
    summary="创建工具注册项",
)
async def create_tool_registry_item(payload: ToolRegistryUpsertRequest):
    """创建新的工具注册项。"""
    try:
        return await tool_registry_service.create_item(payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/tooling/registry/{tool_name}",
    summary="获取工具注册详情",
)
async def get_tool_registry_item(tool_name: str):
    """读取单个工具注册项的详细信息。"""
    try:
        return await tool_registry_service.get_item(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.put(
    "/tooling/registry/{tool_name}",
    summary="更新工具注册项",
)
async def update_tool_registry_item(tool_name: str, payload: ToolRegistryUpsertRequest):
    """更新指定工具的注册信息。"""
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
    """删除指定工具注册项。"""
    return await tool_registry_service.delete_item(tool_name)


@router.post(
    "/tooling/registry/{tool_name}/start",
    summary="启动工具",
)
async def start_tool_registry_item(tool_name: str):
    """将工具标记为上线/启用状态。"""
    try:
        return await tool_registry_service.start(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.post(
    "/tooling/registry/{tool_name}/offline",
    summary="下线工具",
)
async def offline_tool_registry_item(tool_name: str):
    """将工具标记为下线/停用状态。"""
    try:
        return await tool_registry_service.offline(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.get(
    "/tooling/registry/{tool_name}/health",
    summary="工具健康检查",
)
async def tool_registry_item_health(tool_name: str):
    """对单个工具执行健康检查。"""
    try:
        return await tool_registry_service.health(tool_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.post(
    "/tooling/registry/{tool_name}/run",
    summary="执行工具（服务入口）",
)
async def run_tool_registry_item(tool_name: str, payload: ToolRunRequest):
    """绕过 Agent 流程，直接调用工具服务。"""
    try:
        return await tool_registry_service.run(tool_name, payload.input)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")


@router.get(
    "/tooling/connectors",
    summary="获取连接器协议清单",
)
async def get_tool_connectors():
    """列出当前支持的连接器协议和状态。"""
    return await tool_registry_service.connectors()


@router.post(
    "/tooling/connectors/{connector_name}/connect",
    summary="连接连接器",
)
async def connect_tool_connector(connector_name: str):
    """建立指定连接器的连接。"""
    try:
        return await tool_registry_service.connect(connector_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"连接器不存在: {connector_name}")


@router.post(
    "/tooling/connectors/{connector_name}/disconnect",
    summary="断开连接器",
)
async def disconnect_tool_connector(connector_name: str):
    """断开指定连接器。"""
    try:
        return await tool_registry_service.disconnect(connector_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"连接器不存在: {connector_name}")


@router.get(
    "/tooling/connectors/{connector_name}/tools",
    summary="查看连接器可用工具集",
)
async def list_connector_tools(connector_name: str):
    """查看某个连接器暴露的工具列表。"""
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
    """通过连接器协议远程调用一个工具。"""
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
    """读取指定会话的工具调用审计轨迹。

    会优先读取当前 session_id；若轨迹写在 llm_session/runtime_session 下，会自动做一次映射回查。
    """
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
    """基于模拟命令和故障上下文构造工具上下文，验证试跑结果。"""
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


@router.get(
    "/tooling/mcp/servers",
    response_model=list[MCPServerConfig],
    summary="获取 MCP 服务配置清单",
)
async def list_mcp_servers():
    """获取 MCP 服务配置。"""
    return await mcp_service.list_servers()


@router.post(
    "/tooling/mcp/servers",
    response_model=MCPServerConfig,
    summary="创建或更新 MCP 服务配置",
)
async def upsert_mcp_server(payload: MCPServerUpsertRequest):
    """创建或更新 MCP 服务配置。"""
    model = MCPServerConfig(**payload.model_dump(mode="json"))
    return await mcp_service.upsert_server(model)


@router.delete(
    "/tooling/mcp/servers/{server_id}",
    summary="删除 MCP 服务配置",
)
async def delete_mcp_server(server_id: str):
    """删除指定 MCP 服务。"""
    deleted = await mcp_service.delete_server(server_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"MCP 服务不存在: {server_id}")
    return {"deleted": True, "server_id": server_id}


@router.post(
    "/tooling/mcp/servers/{server_id}/probe",
    summary="探测 MCP 服务可用性",
)
async def probe_mcp_server(server_id: str):
    """对指定 MCP 服务执行一次探测。"""
    result = await mcp_service.probe_server(server_id)
    if not bool(result.get("ok")) and str(result.get("error") or "") == "server_not_found":
        raise HTTPException(status_code=404, detail=f"MCP 服务不存在: {server_id}")
    return result


@router.get(
    "/tooling/mcp/bindings",
    response_model=AgentMCPBindingConfig,
    summary="获取 Agent 与 MCP 绑定配置",
)
async def get_mcp_bindings():
    """获取 Agent MCP 绑定。"""
    return await mcp_service.get_bindings()


@router.put(
    "/tooling/mcp/bindings",
    response_model=AgentMCPBindingConfig,
    summary="更新 Agent 与 MCP 绑定配置",
)
async def update_mcp_bindings(payload: AgentMCPBindingConfig):
    """更新 Agent MCP 绑定。"""
    return await mcp_service.update_bindings(payload)
