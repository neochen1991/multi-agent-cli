"""Runbook knowledge provider."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.knowledge_service import knowledge_service
from app.services.tool_context.result import ToolContextResult


async def build_runbook_context(
    service: Any,
    *,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    assigned_command: Optional[Dict[str, Any]],
    command_gate: Dict[str, Any],
) -> ToolContextResult:
    """Build RunbookAgent tool context from knowledge base with legacy fallback."""
    audit_log: List[Dict[str, Any]] = [
        service._audit(  # noqa: SLF001
            tool_name="runbook_case_library",
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
    if not bool(command_gate.get("allow_tool")):
        return ToolContextResult(
            name="runbook_case_library",
            enabled=True,
            used=False,
            status="skipped_by_command",
            summary=f"主Agent命令未要求 RunbookAgent 检索案例：{str(command_gate.get('reason') or '未授权工具调用')}",
            data={"command_preview": service._command_preview(assigned_command)},  # noqa: SLF001
            command_gate=command_gate,
            audit_log=audit_log,
        )
    keywords = service._extract_keywords(compact_context, incident_context, assigned_command)  # noqa: SLF001
    query = " ".join(keywords[:6]).strip()
    knowledge_items = await knowledge_service.search_reference_entries(query=query, limit=8)
    audit_log.append(
        service._audit(  # noqa: SLF001
            tool_name="runbook_case_library",
            action="knowledge_search",
            status="ok" if knowledge_items else "unavailable",
            detail={"query": query, "match_count": len(knowledge_items), "source": "knowledge_base"},
        )
    )
    if knowledge_items:
        return ToolContextResult(
            name="runbook_case_library",
            enabled=True,
            used=True,
            status="ok",
            summary=f"知识库命中 {len(knowledge_items)} 条案例 / SOP。",
            data={"query": query, "items": knowledge_items[:8], "source": "knowledge_base"},
            command_gate=command_gate,
            audit_log=audit_log,
        )
    result = await service._case_library.execute(action="search", query=query)  # noqa: SLF001
    if not result.success:
        error_text = str(result.error or "unknown error")
        return ToolContextResult(
            name="runbook_case_library",
            enabled=True,
            used=False,
            status="error",
            summary=f"案例库查询失败：{error_text}",
            data={"error": error_text, "query": query},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="runbook_case_library",
                    action="case_search",
                    status="error",
                    detail={"error": error_text, "query": query},
                ),
            ],
        )
    payload = result.data if isinstance(result.data, dict) else {}
    raw_items = payload.get("cases")
    if not isinstance(raw_items, list):
        raw_items = payload.get("items")
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    audit_log.append(
        service._audit(  # noqa: SLF001
            tool_name="runbook_case_library",
            action="case_search",
            status="ok",
            detail={"query": query, "match_count": len(items)},
        )
    )
    if not items:
        return ToolContextResult(
            name="runbook_case_library",
            enabled=True,
            used=False,
            status="unavailable",
            summary="案例库无匹配结果，使用默认分析逻辑。",
            data={"query": query},
            command_gate=command_gate,
            audit_log=audit_log,
        )
    return ToolContextResult(
        name="runbook_case_library",
        enabled=True,
        used=True,
        status="ok",
        summary=f"案例库命中 {len(items)} 条相似故障。",
        data={"query": query, "items": items[:8], "source": "legacy_case_library"},
        command_gate=command_gate,
        audit_log=audit_log,
    )
