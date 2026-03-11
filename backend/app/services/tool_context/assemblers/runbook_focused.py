"""Runbook-focused context assembler."""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_runbook_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
    if not isinstance(tool_data, dict):
        tool_data = {}
    items = [item for item in list(tool_data.get("items") or []) if isinstance(item, dict)]
    recommended_actions = service._extract_runbook_actions(items[:6])  # noqa: SLF001
    action_summary = service._build_runbook_action_summary(  # noqa: SLF001
        compact_context=compact_context,
        incident_context=incident_context,
        assigned_command=assigned_command,
        items=items[:6],
        recommended_actions=recommended_actions,
        source=str(tool_data.get("source") or "")[:80],
    )
    return {
        "analysis_objective": {
            "task": str((assigned_command or {}).get("task") or "")[:240],
            "focus": str((assigned_command or {}).get("focus") or "")[:300],
        },
        "knowledge_source": str(tool_data.get("source") or "")[:80],
        "matched_entries": items[:6],
        "recommended_actions": recommended_actions,
        "action_summary": action_summary,
    }
