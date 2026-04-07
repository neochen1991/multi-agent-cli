"""MCP 服务配置与调用聚合服务。"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.models.tooling import AgentMCPBindingConfig, AgentToolingConfig, MCPServerConfig
from app.services.tooling_service import tooling_service


def _norm(text: Any) -> str:
    return str(text or "").strip()


class MCPService:
    """管理 MCP 服务配置、Agent 绑定及基础调用。"""

    async def list_servers(self) -> List[MCPServerConfig]:
        cfg = await tooling_service.get_config()
        return list(cfg.mcp_servers or [])

    async def get_server(self, server_id: str) -> Optional[MCPServerConfig]:
        wanted = _norm(server_id)
        if not wanted:
            return None
        for row in await self.list_servers():
            if _norm(row.id) == wanted:
                return row
        return None

    async def probe_server(self, server_id: str, *, query: str = "mcp health check") -> Dict[str, Any]:
        """对单个 MCP 服务执行一次探测调用。"""
        server = await self.get_server(server_id)
        if not server:
            return {
                "ok": False,
                "server_id": _norm(server_id),
                "error": "server_not_found",
                "items": [],
                "audit_log": [],
            }
        result = await self._collect_from_server(server=server, query=query)
        items = list(result.get("items") or [])
        audit_log = list(result.get("audit_log") or [])
        ok = bool(items) or any(str((row or {}).get("status") or "") == "ok" for row in audit_log if isinstance(row, dict))
        return {
            "ok": ok,
            "server_id": server.id,
            "server_name": server.name,
            "items_count": len(items),
            "items": items[:5],
            "audit_log": audit_log,
        }

    async def upsert_server(self, payload: MCPServerConfig) -> MCPServerConfig:
        cfg = await tooling_service.get_config()
        servers = list(cfg.mcp_servers or [])
        current_id = _norm(payload.id) or f"mcp_{uuid4().hex[:10]}"
        next_item = payload.model_copy(update={"id": current_id})
        replaced = False
        next_rows: List[MCPServerConfig] = []
        for row in servers:
            if _norm(row.id) == current_id:
                next_rows.append(next_item)
                replaced = True
            else:
                next_rows.append(row)
        if not replaced:
            next_rows.append(next_item)
        await tooling_service.update_config(cfg.model_copy(update={"mcp_servers": next_rows}))
        return next_item

    async def delete_server(self, server_id: str) -> bool:
        wanted = _norm(server_id)
        if not wanted:
            return False
        cfg = await tooling_service.get_config()
        servers = list(cfg.mcp_servers or [])
        next_rows = [row for row in servers if _norm(row.id) != wanted]
        if len(next_rows) == len(servers):
            return False
        # 中文注释：删除服务时同步清理各 Agent 绑定中的残留 ID，避免运行时脏引用。
        bindings = dict((cfg.mcp_bindings.bindings if cfg.mcp_bindings else {}) or {})
        for agent_name, ids in list(bindings.items()):
            bindings[agent_name] = [sid for sid in list(ids or []) if _norm(sid) != wanted]
        next_binding = (cfg.mcp_bindings or AgentMCPBindingConfig()).model_copy(update={"bindings": bindings})
        await tooling_service.update_config(cfg.model_copy(update={"mcp_servers": next_rows, "mcp_bindings": next_binding}))
        return True

    async def get_bindings(self) -> AgentMCPBindingConfig:
        cfg = await tooling_service.get_config()
        return cfg.mcp_bindings or AgentMCPBindingConfig()

    async def update_bindings(self, payload: AgentMCPBindingConfig) -> AgentMCPBindingConfig:
        cfg = await tooling_service.get_config()
        await tooling_service.update_config(cfg.model_copy(update={"mcp_bindings": payload}))
        return payload

    async def resolve_agent_servers(self, agent_name: str) -> List[MCPServerConfig]:
        cfg = await tooling_service.get_config()
        binding_cfg = cfg.mcp_bindings or AgentMCPBindingConfig()
        if not bool(binding_cfg.enabled):
            return []
        bound_ids = list((binding_cfg.bindings or {}).get(_norm(agent_name), []) or [])
        if not bound_ids:
            return []
        id_set = {_norm(item) for item in bound_ids if _norm(item)}
        rows: List[MCPServerConfig] = []
        for row in list(cfg.mcp_servers or []):
            if _norm(row.id) in id_set and bool(row.enabled):
                rows.append(row)
        return rows

    async def collect_agent_evidence(
        self,
        *,
        agent_name: str,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """根据 Agent 绑定的 MCP 服务主动抓取日志/监控证据。"""
        if _norm(agent_name) == "LogAgent":
            # 中文注释：LogAgent 若已配置日志文件，自动注入并绑定本地日志 MCP 兜底能力。
            await self._ensure_builtin_local_log_mcp_binding()
        servers = await self.resolve_agent_servers(agent_name)
        if not servers:
            return {
                "enabled": False,
                "used": False,
                "summary": "当前 Agent 未绑定可用 MCP 服务。",
                "servers": [],
                "items": [],
                "audit_log": [],
            }

        focus = " ".join(
            [
                _norm((assigned_command or {}).get("task")),
                _norm((assigned_command or {}).get("focus")),
                _norm(incident_context.get("service_name")),
                _norm(incident_context.get("title")),
                _norm(compact_context.get("error_message")),
                _norm(compact_context.get("trace_id")),
            ]
        ).strip()
        if not focus:
            focus = "incident evidence"

        items: List[Dict[str, Any]] = []
        audit_log: List[Dict[str, Any]] = []
        for server in servers:
            one = await self._collect_from_server(server=server, query=focus)
            items.extend(one.get("items", []))
            audit_log.extend(one.get("audit_log", []))

        used = len(items) > 0
        return {
            "enabled": True,
            "used": used,
            "summary": f"已尝试 MCP 取证：{len(servers)} 个服务，命中 {len(items)} 条数据。",
            "servers": [row.model_dump(mode="json") for row in servers],
            "items": items[:30],
            "audit_log": audit_log,
        }

    async def _ensure_builtin_local_log_mcp_binding(self) -> None:
        """确保内置本地日志 MCP 服务存在且绑定到 LogAgent。"""
        cfg = await tooling_service.get_config()
        log_cfg = cfg.log_file
        log_path = _norm(getattr(log_cfg, "file_path", ""))
        if not bool(getattr(log_cfg, "enabled", False)) or not log_path:
            return

        builtin_id = "builtin_local_log_mcp"
        managed_key = "managed_by"
        managed_value = "system_builtin_local_log_mcp"
        desired_command = [sys.executable, "-m", "app.runtime.mcp.local_log_server"]

        changed = False
        servers = list(cfg.mcp_servers or [])
        found = next((row for row in servers if _norm(row.id) == builtin_id), None)
        if not found:
            servers.append(
                MCPServerConfig(
                    id=builtin_id,
                    name="本地日志文件 MCP",
                    enabled=True,
                    type="local",
                    transport="stdio",
                    protocol_mode="local",
                    command_list=desired_command,
                    env={
                        "MCP_LOG_FILE_PATH": log_path,
                        "MCP_LOG_MAX_LINES": str(int(getattr(log_cfg, "max_lines", 300) or 300)),
                    },
                    capabilities=["logs", "search", "read"],
                    metadata={managed_key: managed_value},
                )
            )
            changed = True
        else:
            if _norm((found.metadata or {}).get(managed_key)) == managed_value:
                patched = found.model_copy(
                    update={
                        "enabled": True,
                        "type": "local",
                        "transport": "stdio",
                        "protocol_mode": "local",
                        "command_list": desired_command,
                        "env": {
                            **dict(found.env or {}),
                            "MCP_LOG_FILE_PATH": log_path,
                            "MCP_LOG_MAX_LINES": str(int(getattr(log_cfg, "max_lines", 300) or 300)),
                        },
                        "capabilities": ["logs", "search", "read"],
                    }
                )
                if patched.model_dump(mode="json") != found.model_dump(mode="json"):
                    servers = [patched if _norm(item.id) == builtin_id else item for item in servers]
                    changed = True

        bindings_cfg = cfg.mcp_bindings or AgentMCPBindingConfig()
        bindings = dict(bindings_cfg.bindings or {})
        log_bindings = [sid for sid in list(bindings.get("LogAgent", []) or []) if _norm(sid)]
        if builtin_id not in log_bindings:
            log_bindings.append(builtin_id)
            bindings["LogAgent"] = log_bindings
            changed = True

        if changed:
            await tooling_service.update_config(
                cfg.model_copy(
                    update={
                        "mcp_servers": servers,
                        "mcp_bindings": bindings_cfg.model_copy(update={"bindings": bindings}),
                    }
                )
            )

    async def _collect_from_server(self, *, server: MCPServerConfig, query: str) -> Dict[str, Any]:
        transport = _norm(server.transport).lower() or "http"
        protocol_mode = _norm(getattr(server, "protocol_mode", "")).lower() or "gateway"
        server_type = _norm(getattr(server, "type", "")).lower() or "remote"
        if transport == "stdio" and (protocol_mode in {"mcp", "local"} or server_type == "local"):
            return await self._collect_via_mcp_stdio(server=server, query=query)
        if protocol_mode == "local" and transport != "stdio":
            return {
                "items": [],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_skip",
                        "status": "skipped",
                        "detail": {
                            "server_id": server.id,
                            "reason": f"protocol_mode=local requires transport=stdio, got {transport}",
                        },
                    }
                ],
            }
        if transport == "stdio":
            return await self._collect_via_stdio(server=server, query=query)
        if protocol_mode == "mcp":
            if transport != "http":
                return {
                    "items": [],
                    "audit_log": [
                        {
                            "tool_name": "mcp_gateway",
                            "action": "mcp_skip",
                            "status": "skipped",
                            "detail": {
                                "server_id": server.id,
                                "reason": f"protocol_mode=mcp currently supports transport=http only, got {transport}",
                            },
                        }
                    ],
                }
            return await self._collect_via_mcp_http(server=server, query=query)
        if transport not in {"http", "sse"}:
            return {
                "items": [],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_skip",
                        "status": "skipped",
                        "detail": {"server_id": server.id, "reason": f"unsupported transport: {transport}"},
                    }
                ],
            }
        endpoint = _norm(server.endpoint)
        if not endpoint:
            return {
                "items": [],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_skip",
                        "status": "skipped",
                        "detail": {"server_id": server.id, "reason": "empty endpoint"},
                    }
                ],
            }

        headers: Dict[str, str] = {}
        token = _norm(server.api_token)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        items: List[Dict[str, Any]] = []
        audit_log: List[Dict[str, Any]] = []
        timeout = max(2, int(server.timeout_seconds or 12))
        caps = [str(item).strip().lower() for item in list(server.capabilities or []) if str(item).strip()]
        for cap in caps:
            path = _norm((server.tool_paths or {}).get(cap))
            if not path:
                continue
            url = f"{endpoint.rstrip('/')}/{path.lstrip('/')}"
            status = "ok"
            detail: Dict[str, Any] = {"server_id": server.id, "capability": cap, "url": url, "query": query[:200]}
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=timeout)) as client:
                    # 中文注释：统一以 query 透传问题焦点，MCP 网关侧可映射为具体检索参数。
                    resp = await client.get(url, headers=headers, params={"query": query})
                    detail["http_status"] = int(resp.status_code)
                    if resp.status_code >= 400:
                        status = "error"
                        detail["error"] = resp.text[:300]
                    else:
                        payload = resp.json()
                        detail["result_count"] = 1
                        items.append(
                            {
                                "server_id": server.id,
                                "server_name": server.name,
                                "capability": cap,
                                "data": payload,
                            }
                        )
            except Exception as exc:
                status = "error"
                detail["error"] = str(exc)
            audit_log.append(
                {
                    "tool_name": "mcp_gateway",
                    "action": "mcp_fetch",
                    "status": status,
                    "detail": detail,
                }
            )
        return {"items": items, "audit_log": audit_log}

    async def _collect_via_mcp_http(self, *, server: MCPServerConfig, query: str) -> Dict[str, Any]:
        """通过标准 MCP JSON-RPC over HTTP 协议拉取证据。"""
        endpoint = _norm(server.endpoint)
        if not endpoint:
            return {
                "items": [],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_skip",
                        "status": "skipped",
                        "detail": {"server_id": server.id, "reason": "empty endpoint"},
                    }
                ],
            }

        timeout = max(2, int(server.timeout_seconds or 12))
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        token = _norm(server.api_token)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        audit_log: List[Dict[str, Any]] = []
        items: List[Dict[str, Any]] = []
        request_id = 1
        session_id = ""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=timeout)) as client:
                init_payload = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "multi-agent-cli-v2", "version": "0.1.0"},
                    },
                }
                request_id += 1
                init_resp = await client.post(endpoint, headers=headers, json=init_payload)
                init_detail: Dict[str, Any] = {"server_id": server.id, "step": "initialize", "http_status": int(init_resp.status_code)}
                if init_resp.status_code >= 400:
                    init_detail["error"] = init_resp.text[:300]
                    audit_log.append(
                        {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "error", "detail": init_detail}
                    )
                    return {"items": [], "audit_log": audit_log}
                init_json = self._safe_json(init_resp)
                if isinstance(init_json, dict) and init_json.get("error"):
                    init_detail["error"] = init_json.get("error")
                    audit_log.append(
                        {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "error", "detail": init_detail}
                    )
                    return {"items": [], "audit_log": audit_log}

                session_id = _norm(
                    init_resp.headers.get("mcp-session-id")
                    or init_resp.headers.get("Mcp-Session-Id")
                    or init_resp.headers.get("x-mcp-session-id")
                )
                if session_id:
                    headers["MCP-Session-Id"] = session_id
                    init_detail["session_id"] = session_id
                audit_log.append(
                    {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "ok", "detail": init_detail}
                )

                # 中文注释：大部分服务要求 initialize 后发送 initialized 通知，作为会话激活信号。
                initialized_payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
                _ = await client.post(endpoint, headers=headers, json=initialized_payload)

                tools_list_payload = {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}}
                request_id += 1
                tools_resp = await client.post(endpoint, headers=headers, json=tools_list_payload)
                tools_detail: Dict[str, Any] = {"server_id": server.id, "step": "tools/list", "http_status": int(tools_resp.status_code)}
                if tools_resp.status_code >= 400:
                    tools_detail["error"] = tools_resp.text[:300]
                    audit_log.append(
                        {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "error", "detail": tools_detail}
                    )
                    return {"items": items, "audit_log": audit_log}
                tools_json = self._safe_json(tools_resp)
                if isinstance(tools_json, dict) and tools_json.get("error"):
                    tools_detail["error"] = tools_json.get("error")
                    audit_log.append(
                        {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "error", "detail": tools_detail}
                    )
                    return {"items": items, "audit_log": audit_log}

                tools = list((((tools_json or {}).get("result") or {}).get("tools") or [])) if isinstance(tools_json, dict) else []
                selected_tools = self._select_mcp_tools(
                    tools=tools,
                    caps=[str(item).strip().lower() for item in list(server.capabilities or []) if str(item).strip()],
                )
                tools_detail["tools_total"] = len(tools)
                tools_detail["tools_selected"] = selected_tools
                tools_detail["result_count"] = len(selected_tools)
                audit_log.append(
                    {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "ok", "detail": tools_detail}
                )
                if not selected_tools:
                    return {"items": items, "audit_log": audit_log}

                for tool_name in selected_tools[:3]:
                    call_payload = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": {"query": query}},
                    }
                    request_id += 1
                    call_resp = await client.post(endpoint, headers=headers, json=call_payload)
                    call_detail: Dict[str, Any] = {
                        "server_id": server.id,
                        "step": "tools/call",
                        "tool_name": tool_name,
                        "http_status": int(call_resp.status_code),
                        "query": query[:200],
                    }
                    if call_resp.status_code >= 400:
                        call_detail["error"] = call_resp.text[:300]
                        audit_log.append(
                            {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "error", "detail": call_detail}
                        )
                        continue
                    call_json = self._safe_json(call_resp)
                    if isinstance(call_json, dict) and call_json.get("error"):
                        call_detail["error"] = call_json.get("error")
                        audit_log.append(
                            {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "error", "detail": call_detail}
                        )
                        continue
                    items.append(
                        {
                            "server_id": server.id,
                            "server_name": server.name,
                            "capability": "mcp",
                            "tool_name": tool_name,
                            "data": ((call_json or {}).get("result") if isinstance(call_json, dict) else call_json),
                        }
                    )
                    call_detail["result_count"] = 1
                    audit_log.append(
                        {"tool_name": "mcp_gateway", "action": "mcp_fetch", "status": "ok", "detail": call_detail}
                    )
            return {"items": items, "audit_log": audit_log}
        except Exception as exc:
            return {
                "items": items,
                "audit_log": [
                    *audit_log,
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_fetch",
                        "status": "error",
                        "detail": {"server_id": server.id, "step": "mcp_http", "session_id": session_id, "error": str(exc)},
                    },
                ],
            }

    async def _collect_via_mcp_stdio(self, *, server: MCPServerConfig, query: str) -> Dict[str, Any]:
        """通过本地 stdio 进程执行标准 MCP 协议调用。"""
        argv = self._build_command_argv(server)
        if not argv:
            return {
                "items": [],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_skip",
                        "status": "skipped",
                        "detail": {"server_id": server.id, "reason": "empty local command"},
                    }
                ],
            }

        timeout = max(2, int(server.timeout_seconds or 12))
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in dict(server.env or {}).items()})
        audit_log: List[Dict[str, Any]] = []
        items: List[Dict[str, Any]] = []
        request_id = 1
        proc: Optional[asyncio.subprocess.Process] = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            init_resp = await self._stdio_rpc_call(
                proc=proc,
                payload={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "multi-agent-cli-v2", "version": "0.1.0"},
                    },
                },
                timeout=timeout,
                request_id=request_id,
            )
            request_id += 1
            if init_resp.get("error"):
                audit_log.append(
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_fetch",
                        "status": "error",
                        "detail": {"server_id": server.id, "step": "initialize", "error": init_resp.get("error")},
                    }
                )
                return {"items": items, "audit_log": audit_log}
            audit_log.append(
                {
                    "tool_name": "mcp_gateway",
                    "action": "mcp_fetch",
                    "status": "ok",
                    "detail": {"server_id": server.id, "step": "initialize"},
                }
            )

            # 中文注释：MCP 协议要求 initialize 之后通知 initialized，服务端才会完全开放工具调用。
            await self._stdio_notify(
                proc=proc,
                payload={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            )

            tools_resp = await self._stdio_rpc_call(
                proc=proc,
                payload={"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}},
                timeout=timeout,
                request_id=request_id,
            )
            request_id += 1
            if tools_resp.get("error"):
                audit_log.append(
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_fetch",
                        "status": "error",
                        "detail": {"server_id": server.id, "step": "tools/list", "error": tools_resp.get("error")},
                    }
                )
                return {"items": items, "audit_log": audit_log}

            tools = list((((tools_resp.get("result") or {}).get("tools")) or []))
            selected_tools = self._select_mcp_tools(
                tools=tools,
                caps=[str(item).strip().lower() for item in list(server.capabilities or []) if str(item).strip()],
            )
            audit_log.append(
                {
                    "tool_name": "mcp_gateway",
                    "action": "mcp_fetch",
                    "status": "ok",
                    "detail": {
                        "server_id": server.id,
                        "step": "tools/list",
                        "tools_total": len(tools),
                        "tools_selected": selected_tools,
                        "result_count": len(selected_tools),
                    },
                }
            )

            for tool_name in selected_tools[:3]:
                call_resp = await self._stdio_rpc_call(
                    proc=proc,
                    payload={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": {"query": query}},
                    },
                    timeout=timeout,
                    request_id=request_id,
                )
                request_id += 1
                if call_resp.get("error"):
                    audit_log.append(
                        {
                            "tool_name": "mcp_gateway",
                            "action": "mcp_fetch",
                            "status": "error",
                            "detail": {
                                "server_id": server.id,
                                "step": "tools/call",
                                "tool_name": tool_name,
                                "error": call_resp.get("error"),
                                "query": query[:200],
                            },
                        }
                    )
                    continue
                items.append(
                    {
                        "server_id": server.id,
                        "server_name": server.name,
                        "capability": "mcp",
                        "tool_name": tool_name,
                        "data": call_resp.get("result"),
                    }
                )
                audit_log.append(
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_fetch",
                        "status": "ok",
                        "detail": {
                            "server_id": server.id,
                            "step": "tools/call",
                            "tool_name": tool_name,
                            "query": query[:200],
                            "result_count": 1,
                        },
                    }
                )

            return {"items": items, "audit_log": audit_log}
        except Exception as exc:
            return {
                "items": items,
                "audit_log": [
                    *audit_log,
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_fetch",
                        "status": "error",
                        "detail": {"server_id": server.id, "step": "mcp_stdio", "error": str(exc), "argv": argv},
                    },
                ],
            }
        finally:
            await self._shutdown_process(proc)

    async def _shutdown_process(self, proc: Optional[asyncio.subprocess.Process]) -> None:
        """关闭本地 MCP 子进程，避免残留僵尸进程。"""
        if not proc:
            return
        try:
            if proc.returncode is None:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=1.5)
        except Exception:
            try:
                if proc.returncode is None:
                    proc.kill()
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
            except Exception:
                return

    def _build_command_argv(self, server: MCPServerConfig) -> List[str]:
        """组装本地启动命令，优先使用命令数组，兼容 command+args 旧格式。"""
        command_list = [str(item).strip() for item in list(getattr(server, "command_list", []) or []) if str(item).strip()]
        if command_list:
            return command_list
        command = _norm(server.command)
        if not command:
            return []
        # 中文注释：command 支持 shell 风格字符串，args 支持 UI 中额外参数列表。
        return [*shlex.split(command), *list(server.args or [])]

    async def _stdio_notify(self, *, proc: asyncio.subprocess.Process, payload: Dict[str, Any]) -> None:
        if not proc.stdin:
            return
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        proc.stdin.write(raw)
        await proc.stdin.drain()

    async def _stdio_rpc_call(
        self,
        *,
        proc: asyncio.subprocess.Process,
        payload: Dict[str, Any],
        timeout: int,
        request_id: int,
    ) -> Dict[str, Any]:
        """发送一条 stdio JSON-RPC 请求并等待对应 id 的响应。"""
        if not proc.stdin or not proc.stdout:
            return {"error": "stdio pipe unavailable"}
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        proc.stdin.write(raw)
        await proc.stdin.drain()

        end_at = asyncio.get_event_loop().time() + float(timeout)
        while True:
            remain = end_at - asyncio.get_event_loop().time()
            if remain <= 0:
                return {"error": f"stdio timeout waiting response id={request_id}"}
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remain)
            if not line:
                return {"error": f"stdio closed before response id={request_id}"}
            text = line.decode("utf-8", errors="ignore").strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except Exception:
                continue
            # 中文注释：忽略通知和其他请求，只消费当前 request_id 对应响应，兼容并发通知流。
            if int(obj.get("id", -1)) != int(request_id):
                continue
            return obj

    def _select_mcp_tools(self, *, tools: List[Dict[str, Any]], caps: List[str]) -> List[str]:
        """按能力关键字从 tools/list 结果里挑选最相关工具。"""
        if not tools:
            return []
        if not caps:
            caps = ["logs", "metrics", "alerts", "traces"]
        scored: List[tuple[int, str]] = []
        for item in tools:
            name = _norm(item.get("name"))
            if not name:
                continue
            name_low = name.lower()
            score = 0
            for cap in caps:
                cap_low = _norm(cap).lower()
                if cap_low and cap_low in name_low:
                    score += 3
            # 中文注释：没有能力关键字命中时，优先兜底 query/search/get 这类检索工具。
            if any(token in name_low for token in ("query", "search", "find", "list", "get")):
                score += 1
            scored.append((score, name))
        scored.sort(key=lambda x: x[0], reverse=True)
        picked = [name for score, name in scored if score > 0]
        if picked:
            return picked[:5]
        return [_norm((tools[0] or {}).get("name"))] if tools else []

    def _safe_json(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except Exception:
            text = resp.text.strip()
            return {"raw": text[:1000]}

    async def _collect_via_stdio(self, *, server: MCPServerConfig, query: str) -> Dict[str, Any]:
        """通过 stdio 模式调用 MCP Server（最小可用协议）。"""
        argv = self._build_command_argv(server)
        if not argv:
            return {
                "items": [],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_skip",
                        "status": "skipped",
                        "detail": {"server_id": server.id, "reason": "empty command"},
                    }
                ],
            }

        timeout = max(2, int(server.timeout_seconds or 12))
        payload = {
            "query": query,
            "capabilities": list(server.capabilities or []),
            "tool_paths": dict(server.tool_paths or {}),
        }
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in dict(server.env or {}).items()})

        detail: Dict[str, Any] = {"server_id": server.id, "argv": argv}
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            raw_in = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            stdout, stderr = await asyncio.wait_for(proc.communicate(input=raw_in), timeout=timeout)
            detail["return_code"] = int(proc.returncode or 0)
            if stderr:
                detail["stderr"] = stderr.decode("utf-8", errors="ignore")[:400]
            if proc.returncode not in {0, None}:
                return {
                    "items": [],
                    "audit_log": [
                        {
                            "tool_name": "mcp_gateway",
                            "action": "mcp_fetch",
                            "status": "error",
                            "detail": detail,
                        }
                    ],
                }
            text = stdout.decode("utf-8", errors="ignore").strip()
            try:
                parsed: Any = json.loads(text) if text else {}
            except Exception:
                parsed = {"raw": text}
            return {
                "items": [
                    {
                        "server_id": server.id,
                        "server_name": server.name,
                        "capability": "stdio",
                        "data": parsed,
                    }
                ],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_fetch",
                        "status": "ok",
                        "detail": detail,
                    }
                ],
            }
        except TimeoutError:
            detail["error"] = f"stdio timeout: {timeout}s"
            return {
                "items": [],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_fetch",
                        "status": "timeout",
                        "detail": detail,
                    }
                ],
            }
        except Exception as exc:
            detail["error"] = str(exc)
            return {
                "items": [],
                "audit_log": [
                    {
                        "tool_name": "mcp_gateway",
                        "action": "mcp_fetch",
                        "status": "error",
                        "detail": detail,
                    }
                ],
            }


mcp_service = MCPService()
