"""Code tool-context provider."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import structlog

from app.models.tooling import AgentToolingConfig
from app.services.tool_context.result import ToolContextResult

logger = structlog.get_logger()


async def build_code_context(
    service: Any,
    *,
    cfg: AgentToolingConfig,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    assigned_command: Optional[Dict[str, Any]],
    command_gate: Dict[str, Any],
) -> ToolContextResult:
    """Build CodeAgent tool context using repository search."""
    tool_cfg = cfg.code_repo
    audit_log: List[Dict[str, Any]] = [
        service._audit(  # noqa: SLF001
            tool_name="git_repo_search",
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
            name="git_repo_search",
            enabled=False,
            used=False,
            status="disabled",
            summary="CodeAgent Git 工具开关已关闭，使用默认分析逻辑。",
            data={},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="git_repo_search",
                    action="config_check",
                    status="disabled",
                    detail={"enabled": False},
                ),
            ],
        )
    if not bool(command_gate.get("allow_tool")):
        return ToolContextResult(
            name="git_repo_search",
            enabled=True,
            used=False,
            status="skipped_by_command",
            summary=f"主Agent命令未要求 CodeAgent 调用 Git 工具：{str(command_gate.get('reason') or '未授权工具调用')}",
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
                name="git_repo_search",
                enabled=True,
                used=False,
                status="unavailable",
                summary="未配置可用仓库地址/本地路径，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        keywords = service._extract_keywords(compact_context, incident_context, assigned_command)  # noqa: SLF001
        hits, scan_meta = await asyncio.to_thread(
            service._search_repo,  # noqa: SLF001
            repo_path,
            keywords,
            int(tool_cfg.max_hits),
        )
        audit_log.append(
            service._audit(  # noqa: SLF001
                tool_name="git_repo_search",
                action="repo_search",
                status="ok",
                detail=scan_meta,
            )
        )
        return ToolContextResult(
            name="git_repo_search",
            enabled=True,
            used=True,
            status="ok",
            summary=f"仓库检索完成，命中 {len(hits)} 条代码片段。",
            data={
                "repo_path": str(repo_path),
                "keywords": keywords,
                "hits": hits[: int(tool_cfg.max_hits)],
            },
            command_gate=command_gate,
            audit_log=audit_log,
        )
    except Exception as exc:
        error_text = str(exc).strip() or exc.__class__.__name__
        logger.warning("code_tool_context_failed", error=error_text)
        return ToolContextResult(
            name="git_repo_search",
            enabled=True,
            used=False,
            status="error",
            summary=f"Git 工具调用失败：{error_text}，已回退默认分析逻辑。",
            data={"error": error_text},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="git_repo_search",
                    action="tool_execute",
                    status="error",
                    detail={"error": error_text},
                ),
            ],
        )
