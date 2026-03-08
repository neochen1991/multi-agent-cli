"""In-memory tool registry and audit helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings
from app.runtime.tool_registry.models import ToolPolicy, ToolRegistryItem


class ToolRegistryService:
    """封装ToolRegistryService相关数据结构或服务能力。"""
    def __init__(self) -> None:
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        # 工具注册中心既要覆盖本地持久化目录，也要覆盖当前工作区。
        # 当前 mock 场景的数据文件放在仓库内的 `mock_data/`，如果这里只保留
        # LOCAL_STORE_DIR，会导致设置页里的路径说明和真实演示数据不一致。
        base_paths = sorted(
            {
                str(Path(settings.LOCAL_STORE_DIR).resolve()),
                str(Path.cwd().resolve()),
            }
        )
        self._items: Dict[str, ToolRegistryItem] = {
            item.tool_name: item
            for item in [
            ToolRegistryItem(
                tool_name="git_repo_search",
                category="repo",
                owner_agent="CodeAgent",
                input_schema={"repo_url": "string", "branch": "string", "keywords": ["string"]},
                policy=ToolPolicy(
                    timeout_seconds=90,
                    audit_level="full",
                    command_whitelist=["git clone", "git fetch", "git log", "git grep"],
                    path_whitelist=base_paths,
                ),
            ),
            ToolRegistryItem(
                tool_name="local_log_reader",
                category="telemetry",
                owner_agent="LogAgent",
                input_schema={"file_path": "string", "max_lines": "int", "keywords": ["string"]},
                policy=ToolPolicy(
                    timeout_seconds=20,
                    audit_level="full",
                    command_whitelist=[],
                    path_whitelist=base_paths,
                ),
            ),
            ToolRegistryItem(
                tool_name="domain_excel_lookup",
                category="asset",
                owner_agent="DomainAgent",
                input_schema={"excel_path": "string", "sheet_name": "string", "max_rows": "int"},
                policy=ToolPolicy(
                    timeout_seconds=20,
                    audit_level="full",
                    command_whitelist=[],
                    path_whitelist=base_paths,
                ),
            ),
            ToolRegistryItem(
                tool_name="db_snapshot_reader",
                category="database",
                owner_agent="DatabaseAgent",
                input_schema={
                    "engine": "string",
                    "db_path": "string",
                    "postgres_dsn": "string",
                    "pg_schema": "string",
                    "max_rows": "int",
                    "keywords": ["string"],
                },
                policy=ToolPolicy(
                    timeout_seconds=25,
                    audit_level="full",
                    command_whitelist=[],
                    path_whitelist=base_paths,
                ),
            ),
            ToolRegistryItem(
                tool_name="metrics_snapshot_analyzer",
                category="telemetry",
                owner_agent="MetricsAgent",
                input_schema={"signals": ["object"]},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="prometheus_connector",
                category="telemetry",
                owner_agent="MetricsAgent",
                input_schema={"endpoint": "string", "query": "string"},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="loki_connector",
                category="telemetry",
                owner_agent="MetricsAgent",
                input_schema={"endpoint": "string", "query": "string", "trace_id": "string"},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="grafana_connector",
                category="telemetry",
                owner_agent="MetricsAgent",
                input_schema={"endpoint": "string", "query": "string", "service": "string"},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="apm_connector",
                category="telemetry",
                owner_agent="MetricsAgent",
                input_schema={"endpoint": "string", "trace_id": "string", "service": "string"},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="logcloud_connector",
                category="telemetry",
                owner_agent="LogAgent",
                input_schema={"endpoint": "string", "query": "string", "trace_id": "string"},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="alert_platform_connector",
                category="alert",
                owner_agent="ProblemAnalysisAgent",
                input_schema={"endpoint": "string", "alert_id": "string", "service": "string"},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="runbook_case_library",
                category="ticket",
                owner_agent="RunbookAgent",
                input_schema={"query": "string"},
                policy=ToolPolicy(timeout_seconds=15, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="rule_suggestion_toolkit",
                category="policy",
                owner_agent="RuleSuggestionAgent",
                input_schema={"metrics_signals": ["object"], "runbook_items": ["object"]},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
        ]
        }
        self._runtime_state: Dict[str, Dict[str, Any]] = {
            name: {"status": "running" if item.enabled else "offline", "last_error": "", "updated_at": ""}
            for name, item in self._items.items()
        }
        self._connector_tools: Dict[str, Dict[str, Any]] = {
            "RepoConnector": {
                "resource": "git_repository",
                "tools": ["git_repo_search", "git_change_window"],
            },
            "TelemetryConnector": {
                "resource": "log_file",
                "tools": [
                    "local_log_reader",
                    "metrics_snapshot_analyzer",
                    "prometheus_connector",
                    "loki_connector",
                    "grafana_connector",
                    "apm_connector",
                    "logcloud_connector",
                ],
            },
            "AssetConnector": {
                "resource": "domain_excel",
                "tools": ["domain_excel_lookup"],
            },
            "DatabaseConnector": {
                "resource": "sqlite_snapshot",
                "tools": ["db_snapshot_reader"],
            },
            "TicketConnector": {
                "resource": "case_library",
                "tools": ["runbook_case_library"],
            },
            "AlertConnector": {
                "resource": "alert_platform",
                "tools": ["alert_platform_connector"],
            },
        }
        self._connector_state: Dict[str, Dict[str, Any]] = {
            name: {
                "connected": True,
                "status": "connected",
                "last_probe_at": "",
                "last_error": "",
                "reconnect_attempts": 0,
                "updated_at": "",
            }
            for name in self._connector_tools.keys()
        }
        self._lock = asyncio.Lock()

    @staticmethod
    def _now_iso() -> str:
        """执行nowiso相关逻辑，并为当前模块提供可复用的处理能力。"""
        return datetime.utcnow().isoformat() + "Z"

    @staticmethod
    def _error_level(error_text: str) -> str:
        """执行errorlevel相关逻辑，并为当前模块提供可复用的处理能力。"""
        text = str(error_text or "").lower()
        if "timeout" in text:
            return "timeout"
        if "forbidden" in text or "unauthorized" in text or "permission" in text:
            return "permission"
        if "not found" in text:
            return "not_found"
        return "runtime"

    async def _probe_connector(self, connector_name: str) -> Dict[str, Any]:
        """执行probe连接器相关逻辑，并为当前模块提供可复用的处理能力。"""
        connector = self._connector_tools.get(connector_name)
        if not connector:
            raise KeyError(connector_name)
        tool_names = list(connector.get("tools") or [])
        enabled_count = 0
        running_count = 0
        async with self._lock:
            state = self._connector_state.setdefault(connector_name, {})
            for name in tool_names:
                item = self._items.get(name)
                runtime = self._runtime_state.get(name) or {}
                if item and bool(item.enabled):
                    enabled_count += 1
                if str(runtime.get("status") or "").lower() == "running":
                    running_count += 1
            connected = bool(state.get("connected", True))
            if not connected and enabled_count > 0:
                # lightweight auto-reconnect probe
                attempts = int(state.get("reconnect_attempts") or 0) + 1
                state["reconnect_attempts"] = attempts
                if attempts <= 3:
                    state["connected"] = True
                    connected = True
                    state["status"] = "reconnected"
                else:
                    state["status"] = "disconnected"
            elif connected:
                state["status"] = "connected" if enabled_count > 0 else "idle"
            state["last_probe_at"] = self._now_iso()
            state["updated_at"] = self._now_iso()
            healthy = connected and (running_count > 0 or enabled_count == 0)
            state["healthy"] = healthy
            state["enabled_tools"] = enabled_count
            state["running_tools"] = running_count
            row = {
                "name": connector_name,
                "resource": str(connector.get("resource") or ""),
                "tools": tool_names,
                **dict(state),
            }
            return row

    async def list_items(self) -> List[Dict[str, Any]]:
        """负责列出items，并返回后续流程可直接消费的数据结果。"""
        async with self._lock:
            rows: List[Dict[str, Any]] = []
            for name, item in self._items.items():
                row = item.model_dump(mode="json")
                row["runtime"] = dict(self._runtime_state.get(name) or {})
                rows.append(row)
        rows.sort(key=lambda row: str(row.get("tool_name") or ""))
        return rows

    async def get_item(self, tool_name: str) -> Dict[str, Any]:
        """负责获取条目，并返回后续流程可直接消费的数据结果。"""
        name = str(tool_name or "").strip()
        async with self._lock:
            item = self._items.get(name)
            if not item:
                raise KeyError(name)
            row = item.model_dump(mode="json")
            row["runtime"] = dict(self._runtime_state.get(name) or {})
            return row

    async def create_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """构建创建条目，供后续节点或调用方直接使用。"""
        item = ToolRegistryItem.model_validate(payload)
        async with self._lock:
            if item.tool_name in self._items:
                raise ValueError(f"工具已存在: {item.tool_name}")
            self._items[item.tool_name] = item
            self._runtime_state[item.tool_name] = {
                "status": "running" if item.enabled else "offline",
                "last_error": "",
                "updated_at": "",
            }
        return await self.get_item(item.tool_name)

    async def update_item(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行更新条目，并同步更新运行时状态、持久化结果或审计轨迹。"""
        name = str(tool_name or "").strip()
        async with self._lock:
            current = self._items.get(name)
            if not current:
                raise KeyError(name)
            merged = {**current.model_dump(mode="json"), **dict(payload or {}), "tool_name": name}
            item = ToolRegistryItem.model_validate(merged)
            self._items[name] = item
            state = self._runtime_state.setdefault(name, {"status": "offline", "last_error": "", "updated_at": ""})
            state["status"] = "running" if item.enabled else "offline"
        return await self.get_item(name)

    async def delete_item(self, tool_name: str) -> Dict[str, Any]:
        """执行删除条目相关逻辑，并为当前模块提供可复用的处理能力。"""
        name = str(tool_name or "").strip()
        async with self._lock:
            existed = name in self._items
            if existed:
                self._items.pop(name, None)
                self._runtime_state.pop(name, None)
        return {"tool_name": name, "deleted": bool(existed)}

    async def start(self, tool_name: str) -> Dict[str, Any]:
        """执行start相关逻辑，并为当前模块提供可复用的处理能力。"""
        name = str(tool_name or "").strip()
        async with self._lock:
            item = self._items.get(name)
            if not item:
                raise KeyError(name)
            item.enabled = True
            state = self._runtime_state.setdefault(name, {})
            state.update({"status": "running", "last_error": "", "updated_at": ""})
        return await self.get_item(name)

    async def offline(self, tool_name: str) -> Dict[str, Any]:
        """执行offline相关逻辑，并为当前模块提供可复用的处理能力。"""
        name = str(tool_name or "").strip()
        async with self._lock:
            item = self._items.get(name)
            if not item:
                raise KeyError(name)
            item.enabled = False
            state = self._runtime_state.setdefault(name, {})
            state.update({"status": "offline", "updated_at": ""})
        return await self.get_item(name)

    async def health(self, tool_name: str) -> Dict[str, Any]:
        """执行健康检查相关逻辑，并为当前模块提供可复用的处理能力。"""
        row = await self.get_item(tool_name)
        runtime = row.get("runtime") if isinstance(row.get("runtime"), dict) else {}
        enabled = bool(row.get("enabled"))
        status = str(runtime.get("status") or ("running" if enabled else "offline"))
        healthy = enabled and status == "running"
        return {
            "tool_name": row.get("tool_name"),
            "enabled": enabled,
            "status": status,
            "healthy": healthy,
            "last_error": str(runtime.get("last_error") or ""),
        }

    async def run(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """负责运行，并处理调用过程中的超时、错误与返回结果。"""
        row = await self.get_item(tool_name)
        runtime = row.get("runtime") if isinstance(row.get("runtime"), dict) else {}
        if not bool(row.get("enabled")) or str(runtime.get("status") or "") == "offline":
            return {
                "tool_name": tool_name,
                "status": "offline",
                "ok": False,
                "message": "tool is offline",
                "input": dict(payload or {}),
            }
        return {
            "tool_name": tool_name,
            "status": "ok",
            "ok": True,
            "message": "tool run accepted",
            "input": dict(payload or {}),
        }

    async def connect(self, connector_name: str) -> Dict[str, Any]:
        """执行connect相关逻辑，并为当前模块提供可复用的处理能力。"""
        if connector_name not in self._connector_tools:
            raise KeyError(connector_name)
        async with self._lock:
            state = self._connector_state.setdefault(connector_name, {})
            state["connected"] = True
            state["status"] = "connected"
            state["last_error"] = ""
            state["last_probe_at"] = self._now_iso()
            state["updated_at"] = self._now_iso()
            state["reconnect_attempts"] = 0
        return await self._probe_connector(connector_name)

    async def disconnect(self, connector_name: str) -> Dict[str, Any]:
        """执行disconnect相关逻辑，并为当前模块提供可复用的处理能力。"""
        if connector_name not in self._connector_tools:
            raise KeyError(connector_name)
        async with self._lock:
            state = self._connector_state.setdefault(connector_name, {})
            state["connected"] = False
            state["status"] = "disconnected"
            state["last_probe_at"] = self._now_iso()
            state["updated_at"] = self._now_iso()
        return await self._probe_connector(connector_name)

    async def list_tools(self, connector_name: str) -> Dict[str, Any]:
        """负责列出tools，并返回后续流程可直接消费的数据结果。"""
        if connector_name not in self._connector_tools:
            raise KeyError(connector_name)
        connector = self._connector_tools[connector_name]
        tool_rows: List[Dict[str, Any]] = []
        for name in list(connector.get("tools") or []):
            try:
                tool_rows.append(await self.get_item(name))
            except KeyError:
                continue
        return {
            "connector": connector_name,
            "resource": str(connector.get("resource") or ""),
            "count": len(tool_rows),
            "items": tool_rows,
        }

    async def call_tool(
        self,
        connector_name: str,
        tool_name: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """负责调用工具，并处理调用过程中的超时、错误与返回结果。"""
        if connector_name not in self._connector_tools:
            raise KeyError(connector_name)
        connector = self._connector_tools[connector_name]
        tool_names = list(connector.get("tools") or [])
        if tool_name not in tool_names:
            raise ValueError(f"{tool_name} 不属于 {connector_name}")
        state = await self._probe_connector(connector_name)
        if not bool(state.get("connected")):
            return {
                "connector": connector_name,
                "tool_name": tool_name,
                "status": "disconnected",
                "ok": False,
                "error_level": "runtime",
                "message": "connector is disconnected",
                "input": dict(payload or {}),
            }
        started = datetime.utcnow()
        try:
            result = await self.run(tool_name, payload)
            duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            async with self._lock:
                current = self._connector_state.setdefault(connector_name, {})
                current["status"] = "connected"
                current["last_error"] = ""
                current["last_probe_at"] = self._now_iso()
                current["updated_at"] = self._now_iso()
            return {
                "connector": connector_name,
                "tool_name": tool_name,
                "status": "ok",
                "ok": bool(result.get("ok", True)),
                "duration_ms": duration_ms,
                "input": dict(payload or {}),
                "result": result,
            }
        except Exception as exc:
            duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            error_text = str(exc).strip() or exc.__class__.__name__
            async with self._lock:
                current = self._connector_state.setdefault(connector_name, {})
                current["status"] = "degraded"
                current["last_error"] = error_text
                current["last_probe_at"] = self._now_iso()
                current["updated_at"] = self._now_iso()
                current["reconnect_attempts"] = int(current.get("reconnect_attempts") or 0) + 1
            return {
                "connector": connector_name,
                "tool_name": tool_name,
                "status": "error",
                "ok": False,
                "duration_ms": duration_ms,
                "error": error_text,
                "error_level": self._error_level(error_text),
                "input": dict(payload or {}),
            }

    async def connectors(self) -> List[Dict[str, Any]]:
        """执行connectors相关逻辑，并为当前模块提供可复用的处理能力。"""
        rows: List[Dict[str, Any]] = []
        for name in self._connector_tools.keys():
            rows.append(await self._probe_connector(name))
        rows.sort(key=lambda row: str(row.get("name") or ""))
        return rows


tool_registry_service = ToolRegistryService()
