"""专家 Agent 扩展 Tool 插件执行网关。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional

from app.services.tool_plugin_loader import ToolPluginLoader, ToolPluginProfile


class ToolPluginGateway:
    """根据插件元数据执行扩展 Tool，并返回结构化结果。"""

    def __init__(self, plugins_root: Path | str = "backend/extensions/tools") -> None:
        self._plugins_root = Path(plugins_root)

    def invoke_for_agent(
        self,
        *,
        agent_name: str,
        requested_tools: List[str],
        payload: Dict[str, Any],
        plugins_dir: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        allowlist: Optional[List[str]] = None,
        max_calls: int = 3,
    ) -> List[Dict[str, Any]]:
        """按当前 Agent 权限执行请求的插件工具。"""
        picks = [str(item or "").strip() for item in requested_tools if str(item or "").strip()]
        if not picks:
            return []
        loader = ToolPluginLoader(Path(plugins_dir).expanduser() if plugins_dir else self._plugins_root)
        allowed_tools = {str(item or "").strip() for item in (allowlist or []) if str(item or "").strip()}
        outputs: List[Dict[str, Any]] = []
        for tool_id in list(dict.fromkeys(picks))[: max(1, int(max_calls or 1))]:
            if allowed_tools and tool_id not in allowed_tools:
                continue
            plugin = loader.get(tool_id)
            if plugin is None:
                continue
            if plugin.allowed_agents and agent_name not in plugin.allowed_agents:
                continue
            result = self._invoke_plugin(
                plugin=plugin,
                payload={**dict(payload or {}), "agent_name": agent_name},
                timeout_seconds=timeout_seconds,
            )
            outputs.append({"tool_name": plugin.tool_id, **result})
        return outputs

    def _invoke_plugin(
        self,
        *,
        plugin: ToolPluginProfile,
        payload: Dict[str, Any],
        timeout_seconds: Optional[int],
    ) -> Dict[str, Any]:
        if str(plugin.runtime or "").strip().lower() != "python":
            return {
                "success": False,
                "status": "unsupported_runtime",
                "summary": f"插件 {plugin.tool_id} runtime={plugin.runtime} 暂不支持。",
            }
        entry = Path(plugin.tool_path) / str(plugin.entry or "run.py")
        if not entry.exists():
            return {
                "success": False,
                "status": "entry_missing",
                "summary": f"插件 {plugin.tool_id} 缺少入口文件 {plugin.entry}",
            }

        repo_root = Path.cwd()
        backend_root = repo_root / "backend"
        env = dict(os.environ)
        pythonpath_items = [
            str(backend_root),
            str(repo_root),
            *(env.get("PYTHONPATH", "").split(os.pathsep) if env.get("PYTHONPATH") else []),
        ]
        env["PYTHONPATH"] = os.pathsep.join(item for item in pythonpath_items if item)
        timeout = int(timeout_seconds or plugin.timeout_seconds or 60)

        try:
            completed = subprocess.run(
                [sys.executable, str(entry)],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                check=False,
                timeout=max(5, timeout),
                cwd=str(repo_root),
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "status": "timeout",
                "timed_out": True,
                "summary": f"插件 {plugin.tool_id} 执行超时",
            }

        if int(completed.returncode) != 0:
            return {
                "success": False,
                "status": "failed",
                "summary": str(completed.stderr or "").strip() or f"插件 {plugin.tool_id} 执行失败",
            }

        try:
            parsed = json.loads(completed.stdout or "{}")
        except Exception:
            return {
                "success": False,
                "status": "invalid_output",
                "summary": f"插件 {plugin.tool_id} 输出不是合法 JSON",
            }
        if isinstance(parsed, dict):
            parsed.setdefault("success", True)
            parsed.setdefault("status", "ok")
            return parsed
        return {
            "success": False,
            "status": "invalid_output",
            "summary": f"插件 {plugin.tool_id} 输出不是对象",
        }
