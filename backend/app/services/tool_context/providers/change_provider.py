"""Change tool-context provider."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.models.tooling import AgentToolingConfig
from app.services.tool_context.result import ToolContextResult


async def build_change_context(
    service: Any,
    *,
    cfg: AgentToolingConfig,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    assigned_command: Optional[Dict[str, Any]],
    command_gate: Dict[str, Any],
) -> ToolContextResult:
    """Build ChangeAgent tool context from recent git changes."""
    tool_cfg = cfg.code_repo
    audit_log: List[Dict[str, Any]] = [
        service._audit(  # noqa: SLF001
            tool_name="git_change_window",
            action="command_gate",
            status="ok" if command_gate.get("allow_tool") else "skipped",
            detail={
                "reason": str(command_gate.get("reason") or ""),
                "has_command": bool(command_gate.get("has_command")),
                "decision_source": str(command_gate.get("decision_source") or ""),
                "command_preview": service._command_preview(assigned_command),  # noqa: SLF001
            },
        )
    ]
    if not tool_cfg.enabled:
        return ToolContextResult(
            name="git_change_window",
            enabled=False,
            used=False,
            status="disabled",
            summary="ChangeAgent 变更工具开关已关闭，使用默认分析逻辑。",
            data={},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="git_change_window",
                    action="config_check",
                    status="disabled",
                    detail={"enabled": False},
                ),
            ],
        )
    if not bool(command_gate.get("allow_tool")):
        return ToolContextResult(
            name="git_change_window",
            enabled=True,
            used=False,
            status="skipped_by_command",
            summary=f"主Agent命令未要求 ChangeAgent 拉取变更窗口：{str(command_gate.get('reason') or '未授权工具调用')}",
            data={"command_preview": service._command_preview(assigned_command)},  # noqa: SLF001
            command_gate=command_gate,
            audit_log=audit_log,
        )
    try:
        repo_path = await asyncio.to_thread(
            service._resolve_repo_path,  # noqa: SLF001
            tool_cfg.repo_url,
            tool_cfg.access_token,
            tool_cfg.branch,
            tool_cfg.local_repo_path,
            audit_log,
        )
        if not repo_path:
            return ToolContextResult(
                name="git_change_window",
                enabled=True,
                used=False,
                status="unavailable",
                summary="未配置可用仓库地址/本地路径，无法拉取变更窗口。",
                data={},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        changes = await asyncio.to_thread(
            service._collect_recent_git_changes,  # noqa: SLF001
            repo_path,
            int(getattr(tool_cfg, "max_hits", 20) or 20),
            audit_log,
        )
        if not changes:
            return ToolContextResult(
                name="git_change_window",
                enabled=True,
                used=False,
                status="unavailable",
                summary="未获取到有效变更记录，已回退默认分析逻辑。",
                data={"repo_path": repo_path, "changes": []},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        return ToolContextResult(
            name="git_change_window",
            enabled=True,
            used=True,
            status="ok",
            summary=f"已提取最近 {len(changes)} 条代码变更。",
            data={"repo_path": repo_path, "changes": changes},
            command_gate=command_gate,
            audit_log=audit_log,
        )
    except Exception as exc:
        error_text = str(exc).strip() or exc.__class__.__name__
        return ToolContextResult(
            name="git_change_window",
            enabled=True,
            used=False,
            status="error",
            summary=f"变更窗口提取失败：{error_text}，已回退默认分析。",
            data={"error": error_text},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="git_change_window",
                    action="tool_execute",
                    status="error",
                    detail={"error": error_text},
                ),
            ],
        )
