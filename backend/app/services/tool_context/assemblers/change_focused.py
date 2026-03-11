"""Change-focused context assembler."""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_change_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
    if not isinstance(tool_data, dict):
        tool_data = {}
    leads = service._extract_investigation_leads(compact_context, incident_context, assigned_command)  # noqa: SLF001
    changes = [item for item in list(tool_data.get("changes") or []) if isinstance(item, dict)]
    causal_summary = service._build_change_causal_summary(  # noqa: SLF001
        compact_context=compact_context,
        incident_context=incident_context,
        assigned_command=assigned_command,
        changes=changes,
    )
    return {
        "analysis_objective": {
            "task": str((assigned_command or {}).get("task") or "")[:240],
            "focus": str((assigned_command or {}).get("focus") or "")[:300],
        },
        "service_scope": {
            "service_name": service._primary_service_name(compact_context, incident_context, assigned_command),  # noqa: SLF001
            "api_endpoints": list(leads.get("api_endpoints") or [])[:8],
            "code_artifacts": list(leads.get("code_artifacts") or [])[:10],
        },
        "change_window": changes[:12],
        "causal_summary": causal_summary,
    }
