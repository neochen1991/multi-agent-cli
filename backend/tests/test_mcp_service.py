"""MCP 配置与取证服务测试。"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from app.models.tooling import AgentMCPBindingConfig, MCPServerConfig
from app.repositories.tooling_repository import InMemoryToolingRepository
from app.services.agent_tool_context_service import AgentToolContextService
from app.services.mcp_service import MCPService
from app.services.tool_context.result import ToolContextResult
from app.services.tooling_service import ToolingService


@pytest.mark.asyncio
async def test_mcp_service_delete_server_also_cleans_agent_bindings(monkeypatch: pytest.MonkeyPatch):
    """删除 MCP 服务时应同步清理 Agent 绑定残留。"""

    local_tooling = ToolingService(repository=InMemoryToolingRepository())
    monkeypatch.setattr("app.services.mcp_service.tooling_service", local_tooling)
    service = MCPService()

    await service.upsert_server(
        MCPServerConfig(
            id="mcp_logs",
            name="日志 MCP",
            enabled=True,
            capabilities=["logs"],
            endpoint="http://mcp.example.internal",
        )
    )
    await service.update_bindings(
        AgentMCPBindingConfig(
            enabled=True,
            bindings={
                "LogAgent": ["mcp_logs"],
                "MetricsAgent": ["mcp_logs", "mcp_other"],
            },
        )
    )

    deleted = await service.delete_server("mcp_logs")
    assert deleted is True

    bindings = await service.get_bindings()
    assert bindings.bindings["LogAgent"] == []
    assert bindings.bindings["MetricsAgent"] == ["mcp_other"]


@pytest.mark.asyncio
async def test_collect_agent_evidence_uses_bound_servers(monkeypatch: pytest.MonkeyPatch):
    """绑定 MCP 服务后，专家 Agent 应拿到结构化取证结果。"""

    local_tooling = ToolingService(repository=InMemoryToolingRepository())
    monkeypatch.setattr("app.services.mcp_service.tooling_service", local_tooling)
    service = MCPService()

    await service.upsert_server(
        MCPServerConfig(
            id="mcp_metrics",
            name="指标 MCP",
            enabled=True,
            capabilities=["metrics"],
            endpoint="http://mcp.example.internal",
        )
    )
    await service.update_bindings(
        AgentMCPBindingConfig(
            enabled=True,
            bindings={"MetricsAgent": ["mcp_metrics"]},
        )
    )

    async def _fake_collect_from_server(*, server: MCPServerConfig, query: str) -> Dict[str, Any]:
        return {
            "items": [
                {
                    "server_id": server.id,
                    "server_name": server.name,
                    "capability": "metrics",
                    "data": {"query": query, "series": [{"name": "error_rate", "value": 0.32}]},
                }
            ],
            "audit_log": [
                {
                    "tool_name": "mcp_gateway",
                    "action": "mcp_fetch",
                    "status": "ok",
                    "detail": {"server_id": server.id},
                }
            ],
        }

    monkeypatch.setattr(service, "_collect_from_server", _fake_collect_from_server)

    result = await service.collect_agent_evidence(
        agent_name="MetricsAgent",
        compact_context={"error_message": "502 timeout"},
        incident_context={"service_name": "order-service", "title": "订单接口异常"},
        assigned_command={"task": "分析错误率上升原因"},
    )

    assert result["enabled"] is True
    assert result["used"] is True
    assert len(result["items"]) == 1
    assert result["items"][0]["capability"] == "metrics"


@pytest.mark.asyncio
async def test_merge_mcp_context_promotes_none_result_to_mcp_gateway(monkeypatch: pytest.MonkeyPatch):
    """当基础工具未命中但 MCP 命中时，应切换为 mcp_gateway 上下文。"""

    service = AgentToolContextService()

    async def _fake_collect_agent_evidence(**_: Any) -> Dict[str, Any]:
        return {
            "enabled": True,
            "used": True,
            "summary": "已尝试 MCP 取证：1 个服务，命中 2 条数据。",
            "servers": [{"id": "mcp_logs"}],
            "items": [{"server_id": "mcp_logs", "capability": "logs", "data": {"hits": 2}}],
            "audit_log": [{"action": "mcp_fetch", "status": "ok", "detail": {"server_id": "mcp_logs"}}],
        }

    monkeypatch.setattr("app.services.agent_tool_context_service.mcp_service.collect_agent_evidence", _fake_collect_agent_evidence)

    base = ToolContextResult(
        name="none",
        enabled=False,
        used=False,
        status="skipped",
        summary="当前 Agent 无外部工具配置。",
        data={},
        command_gate={"has_command": True, "allow_tool": True},
    )
    merged = await service._merge_mcp_context(  # noqa: SLF001 - 验证内部 MCP 合并逻辑
        result=base,
        agent_name="LogAgent",
        compact_context={},
        incident_context={},
        assigned_command={"task": "抓取日志证据"},
    )

    assert merged.name == "mcp_gateway"
    assert merged.used is True
    assert "mcp_context" in merged.data


@pytest.mark.asyncio
async def test_collect_from_server_uses_mcp_protocol_mode(monkeypatch: pytest.MonkeyPatch):
    """protocol_mode=mcp 时应走标准 MCP 协议分支。"""

    service = MCPService()

    async def _fake_collect_via_mcp_http(*, server: MCPServerConfig, query: str) -> Dict[str, Any]:
        return {
            "items": [{"server_id": server.id, "capability": "mcp", "data": {"query": query}}],
            "audit_log": [{"action": "mcp_fetch", "status": "ok", "detail": {"path": "mcp_http"}}],
        }

    monkeypatch.setattr(service, "_collect_via_mcp_http", _fake_collect_via_mcp_http)

    result = await service._collect_from_server(  # noqa: SLF001 - 验证协议路由分支
        server=MCPServerConfig(
            id="mcp_std",
            name="标准 MCP",
            enabled=True,
            transport="http",
            protocol_mode="mcp",
            endpoint="https://example-mcp.internal/mcp",
            capabilities=["logs"],
        ),
        query="orders timeout",
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["capability"] == "mcp"


@pytest.mark.asyncio
async def test_collect_from_server_local_mode_uses_mcp_stdio(monkeypatch: pytest.MonkeyPatch):
    """local 模式下应通过 stdio 走标准 MCP 调用。"""

    service = MCPService()

    async def _fake_collect_via_mcp_stdio(*, server: MCPServerConfig, query: str) -> Dict[str, Any]:
        return {
            "items": [{"server_id": server.id, "capability": "mcp", "data": {"query": query}}],
            "audit_log": [{"action": "mcp_fetch", "status": "ok", "detail": {"path": "mcp_stdio"}}],
        }

    monkeypatch.setattr(service, "_collect_via_mcp_stdio", _fake_collect_via_mcp_stdio)

    result = await service._collect_from_server(  # noqa: SLF001 - 验证协议路由分支
        server=MCPServerConfig(
            id="mcp_local",
            name="本地 MCP",
            enabled=True,
            type="local",
            transport="stdio",
            protocol_mode="local",
            command_list=["python", "-m", "my_local_mcp"],
            capabilities=["logs"],
        ),
        query="orders timeout",
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["capability"] == "mcp"


@pytest.mark.asyncio
async def test_collect_agent_evidence_auto_binds_builtin_local_log_mcp(monkeypatch: pytest.MonkeyPatch):
    """LogAgent 在配置本地日志后应自动具备并绑定内置 local-log MCP。"""

    local_tooling = ToolingService(repository=InMemoryToolingRepository())
    monkeypatch.setattr("app.services.mcp_service.tooling_service", local_tooling)
    cfg = await local_tooling.get_config()
    cfg = cfg.model_copy(
        update={
            "log_file": cfg.log_file.model_copy(update={"enabled": True, "file_path": "/tmp/app.log", "max_lines": 220}),
        }
    )
    await local_tooling.update_config(cfg)
    service = MCPService()

    async def _fake_collect_from_server(*, server: MCPServerConfig, query: str) -> Dict[str, Any]:
        return {
            "items": [{"server_id": server.id, "capability": "mcp", "data": {"query": query}}],
            "audit_log": [{"action": "mcp_fetch", "status": "ok", "detail": {"server_id": server.id}}],
        }

    monkeypatch.setattr(service, "_collect_from_server", _fake_collect_from_server)

    result = await service.collect_agent_evidence(
        agent_name="LogAgent",
        compact_context={"error_message": "timeout"},
        incident_context={"service_name": "order-service"},
        assigned_command={"task": "collect logs"},
    )
    assert result["enabled"] is True
    assert result["used"] is True

    bindings = await service.get_bindings()
    assert "builtin_local_log_mcp" in list(bindings.bindings.get("LogAgent", []))
    builtin = await service.get_server("builtin_local_log_mcp")
    assert builtin is not None
    assert builtin.type == "local"
    assert builtin.transport == "stdio"
    assert builtin.protocol_mode == "local"
    assert builtin.command_list


@pytest.mark.asyncio
async def test_probe_server_returns_not_found(monkeypatch: pytest.MonkeyPatch):
    """探测不存在服务时返回 server_not_found。"""

    local_tooling = ToolingService(repository=InMemoryToolingRepository())
    monkeypatch.setattr("app.services.mcp_service.tooling_service", local_tooling)
    service = MCPService()

    result = await service.probe_server("missing_server")
    assert result["ok"] is False
    assert result["error"] == "server_not_found"
