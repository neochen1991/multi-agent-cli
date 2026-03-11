"""Log tool-context provider."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.models.tooling import AgentToolingConfig
from app.services.tool_context.result import ToolContextResult

logger = structlog.get_logger()


async def build_log_context(
    service: Any,
    *,
    cfg: AgentToolingConfig,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    assigned_command: Optional[Dict[str, Any]],
    command_gate: Dict[str, Any],
) -> ToolContextResult:
    """Build LogAgent tool context using local log file and optional log cloud."""
    tool_cfg = cfg.log_file
    audit_log: List[Dict[str, Any]] = [
        service._audit(  # noqa: SLF001
            tool_name="local_log_reader",
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
            name="local_log_reader",
            enabled=False,
            used=False,
            status="disabled",
            summary="LogAgent 日志文件工具开关已关闭，使用默认分析逻辑。",
            data={},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="local_log_reader",
                    action="config_check",
                    status="disabled",
                    detail={"enabled": False},
                ),
            ],
        )
    if not bool(command_gate.get("allow_tool")):
        return ToolContextResult(
            name="local_log_reader",
            enabled=True,
            used=False,
            status="skipped_by_command",
            summary=f"主Agent命令未要求 LogAgent 读取日志：{str(command_gate.get('reason') or '未授权工具调用')}",
            data={"command_preview": service._command_preview(assigned_command)},  # noqa: SLF001
            command_gate=command_gate,
            audit_log=audit_log,
        )

    path = Path(str(tool_cfg.file_path or "").strip())
    if not path.exists() or not path.is_file():
        return ToolContextResult(
            name="local_log_reader",
            enabled=True,
            used=False,
            status="unavailable",
            summary="日志文件路径不可用，已回退默认分析逻辑。",
            data={"file_path": str(path)},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="local_log_reader",
                    action="file_check",
                    status="unavailable",
                    detail={"file_path": str(path)},
                ),
            ],
        )

    try:
        keywords = service._extract_keywords(compact_context, incident_context, assigned_command)  # noqa: SLF001
        service_name = service._primary_service_name(compact_context, incident_context, assigned_command)  # noqa: SLF001
        trace_id = service._primary_trace_id(compact_context, incident_context, assigned_command)  # noqa: SLF001
        remote_logcloud_payload: Dict[str, Any] = {}
        if bool(getattr(cfg, "logcloud_source", None) and cfg.logcloud_source.enabled):
            logcloud_result = await service._logcloud_connector.fetch(  # noqa: SLF001
                cfg.logcloud_source,
                {
                    "service_name": service_name,
                    "trace_id": trace_id,
                    "query": " ".join(keywords[:6]),
                },
            )
            logcloud_status = str(logcloud_result.get("status") or "unknown")
            logcloud_request_meta = dict(logcloud_result.get("request_meta") or {})
            audit_log.append(
                service._audit(  # noqa: SLF001
                    tool_name="logcloud_connector",
                    action="remote_fetch",
                    status=logcloud_status,
                    detail={
                        "enabled": bool(cfg.logcloud_source.enabled),
                        "endpoint": str(cfg.logcloud_source.endpoint or "")[:180],
                        "message": str(logcloud_result.get("message") or "")[:180],
                        "request_meta": logcloud_request_meta,
                    },
                )
            )
            if logcloud_status == "ok" and isinstance(logcloud_result.get("data"), dict):
                remote_logcloud_payload = dict(logcloud_result.get("data") or {})

        excerpt, line_count, read_meta = await asyncio.to_thread(
            service._read_log_excerpt,  # noqa: SLF001
            path,
            int(tool_cfg.max_lines),
            keywords,
        )
        audit_log.append(
            service._audit(  # noqa: SLF001
                tool_name="local_log_reader",
                action="file_read",
                status="ok",
                detail=read_meta,
            )
        )
        return ToolContextResult(
            name="local_log_reader",
            enabled=True,
            used=True,
            status="ok",
            summary=f"日志文件读取完成，采样 {line_count} 行。",
            data={
                "file_path": str(path),
                "line_count": line_count,
                "keywords": keywords,
                "excerpt": excerpt,
                "remote_logcloud": {
                    "enabled": bool(getattr(cfg, "logcloud_source", None) and cfg.logcloud_source.enabled),
                    "status": "ok" if remote_logcloud_payload else "disabled_or_unavailable",
                    "payload": remote_logcloud_payload,
                },
            },
            command_gate=command_gate,
            audit_log=audit_log,
        )
    except Exception as exc:
        error_text = str(exc).strip() or exc.__class__.__name__
        logger.warning("log_tool_context_failed", error=error_text)
        return ToolContextResult(
            name="local_log_reader",
            enabled=True,
            used=False,
            status="error",
            summary=f"日志文件读取失败：{error_text}，已回退默认分析逻辑。",
            data={"error": error_text},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="local_log_reader",
                    action="file_read",
                    status="error",
                    detail={"error": error_text, "file_path": str(path)},
                ),
            ],
        )
