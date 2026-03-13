"""Domain tool-context provider."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.models.tooling import AgentToolingConfig
from app.services.asset_service import asset_service
from app.services.tool_context.result import ToolContextResult

logger = structlog.get_logger()


async def build_domain_context(
    service: Any,
    *,
    cfg: AgentToolingConfig,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    assigned_command: Optional[Dict[str, Any]],
    command_gate: Dict[str, Any],
) -> ToolContextResult:
    """Build DomainAgent tool context from responsibility asset file and CMDB."""
    tool_cfg = cfg.domain_excel
    audit_log: List[Dict[str, Any]] = [
        service._audit(  # noqa: SLF001
            tool_name="domain_excel_lookup",
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

    log_content = str(
        (compact_context.get("log_content") or incident_context.get("log_content") or "")
    ).strip()
    symptom = str(
        (incident_context.get("description") or incident_context.get("title") or "")
    ).strip()
    responsibility_hit = None
    if log_content or symptom:
        try:
            responsibility_hit = await asset_service.locate_responsibility_assets(
                log_content=log_content,
                symptom=symptom,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("responsibility_asset_lookup_failed", error=str(exc))
            audit_log.append(
                service._audit(  # noqa: SLF001
                    tool_name="domain_responsibility_assets",
                    action="local_lookup",
                    status="error",
                    detail={"error": str(exc)},
                )
            )
    if log_content or symptom:
        audit_log.append(
            service._audit(  # noqa: SLF001
                tool_name="domain_responsibility_assets",
                action="local_lookup",
                status="ok" if responsibility_hit else "miss",
                detail={
                    "matched": bool(responsibility_hit and responsibility_hit.get("matched")),
                    "asset_id": str((responsibility_hit or {}).get("responsibility_asset_id") or ""),
                },
            )
        )
    if responsibility_hit and responsibility_hit.get("matched"):
        return ToolContextResult(
            name="domain_responsibility_assets",
            enabled=True,
            used=True,
            status="ok",
            summary="已命中系统责任田资产，跳过 Excel 责任田查询。",
            data={
                "source": "responsibility_assets",
                "matched": True,
                "mapping": responsibility_hit,
            },
            command_gate=command_gate,
            audit_log=audit_log,
        )

    if not tool_cfg.enabled:
        return ToolContextResult(
            name="domain_excel_lookup",
            enabled=False,
            used=False,
            status="disabled",
            summary="DomainAgent 责任田 Excel 工具开关已关闭，使用默认分析逻辑。",
            data={},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="domain_excel_lookup",
                    action="config_check",
                    status="disabled",
                    detail={"enabled": False},
                ),
            ],
        )
    if not bool(command_gate.get("allow_tool")):
        return ToolContextResult(
            name="domain_excel_lookup",
            enabled=True,
            used=False,
            status="skipped_by_command",
            summary=f"主Agent命令未要求 DomainAgent 查询责任田文档：{str(command_gate.get('reason') or '未授权工具调用')}",
            data={"command_preview": service._command_preview(assigned_command)},  # noqa: SLF001
            command_gate=command_gate,
            audit_log=audit_log,
        )
    path = Path(str(tool_cfg.excel_path or "").strip())
    if not path.exists() or not path.is_file():
        return ToolContextResult(
            name="domain_excel_lookup",
            enabled=True,
            used=False,
            status="unavailable",
            summary="责任田 Excel 路径不可用，已回退默认分析逻辑。",
            data={"excel_path": str(path)},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="domain_excel_lookup",
                    action="file_check",
                    status="unavailable",
                    detail={"excel_path": str(path)},
                ),
            ],
        )
    try:
        keywords = service._extract_keywords(compact_context, incident_context, assigned_command)  # noqa: SLF001
        service_name = service._primary_service_name(compact_context, incident_context, assigned_command)  # noqa: SLF001
        result = await asyncio.to_thread(
            service._lookup_domain_file,  # noqa: SLF001
            path,
            str(tool_cfg.sheet_name or "").strip(),
            int(tool_cfg.max_rows),
            int(tool_cfg.max_matches),
            keywords,
        )
        cmdb_payload: Dict[str, Any] = {}
        if bool(cfg.cmdb_source.enabled):
            cmdb_result = await service._cmdb_connector.fetch(  # noqa: SLF001
                cfg.cmdb_source,
                {
                    "service_name": service_name,
                    "keywords": keywords[:8],
                },
            )
            cmdb_status = str(cmdb_result.get("status") or "unknown")
            cmdb_request_meta = dict(cmdb_result.get("request_meta") or {})
            audit_log.append(
                service._audit(  # noqa: SLF001
                    tool_name="cmdb_connector",
                    action="remote_fetch",
                    status=cmdb_status,
                    detail={
                        "enabled": bool(cfg.cmdb_source.enabled),
                        "endpoint": str(cfg.cmdb_source.endpoint or "")[:180],
                        "message": str(cmdb_result.get("message") or "")[:180],
                        "request_meta": cmdb_request_meta,
                    },
                )
            )
            if cmdb_status == "ok" and isinstance(cmdb_result.get("data"), dict):
                cmdb_payload = dict(cmdb_result.get("data") or {})
        audit_log.append(
            service._audit(  # noqa: SLF001
                tool_name="domain_excel_lookup",
                action="file_read",
                status="ok",
                detail={
                    "excel_path": str(path),
                    "row_count": int(result.get("row_count") or 0),
                    "match_count": len(list(result.get("matches") or [])),
                    "sheet_used": str(result.get("sheet_used") or ""),
                    "format": str(result.get("format") or ""),
                },
            )
        )
        return ToolContextResult(
            name="domain_excel_lookup",
            enabled=True,
            used=True,
            status="ok",
            summary=f"责任田文档查询完成，命中 {len(result.get('matches') or [])} 行。",
            data={
                "excel_path": str(path),
                "keywords": keywords,
                **result,
                "remote_cmdb": {
                    "enabled": bool(cfg.cmdb_source.enabled),
                    "status": "ok" if cmdb_payload else "disabled_or_unavailable",
                    "payload": cmdb_payload,
                },
            },
            command_gate=command_gate,
            audit_log=audit_log,
        )
    except Exception as exc:
        error_text = str(exc).strip() or exc.__class__.__name__
        logger.warning("domain_tool_context_failed", error=error_text)
        return ToolContextResult(
            name="domain_excel_lookup",
            enabled=True,
            used=False,
            status="error",
            summary=f"责任田文档查询失败：{error_text}，已回退默认分析逻辑。",
            data={"error": error_text},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="domain_excel_lookup",
                    action="file_read",
                    status="error",
                    detail={"error": error_text, "excel_path": str(path)},
                ),
            ],
        )
