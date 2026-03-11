"""Log-focused context assembler."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.log_analysis.timeline_extractor import build_trace_timeline
from app.services.log_analysis.trace_alignment import build_propagation_chain


def build_log_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    excerpt = service._resolve_log_excerpt(compact_context, incident_context, tool_context)  # noqa: SLF001
    timeline = service._extract_log_timeline(excerpt, max_events=10)  # noqa: SLF001
    trace_id = service._primary_trace_id(compact_context, incident_context, assigned_command)  # noqa: SLF001
    causal_timeline = service._build_log_causal_timeline(timeline)  # noqa: SLF001
    tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
    if not isinstance(tool_data, dict):
        tool_data = {}
    trace_timeline = build_trace_timeline(
        timeline_events=timeline,
        trace_id=trace_id,
        service_name=service._primary_service_name(compact_context, incident_context, assigned_command),  # noqa: SLF001
        tool_data=tool_data,
    )
    return {
        "analysis_objective": {
            "task": str((assigned_command or {}).get("task") or "")[:240],
            "focus": str((assigned_command or {}).get("focus") or "")[:300],
        },
        "log_scope": {
            "service_name": service._primary_service_name(compact_context, incident_context, assigned_command),  # noqa: SLF001
            "trace_id": trace_id,
            "keywords": list(((tool_context or {}).get("data") or {}).get("keywords") or [])[:10] if isinstance(tool_context, dict) else [],
        },
        "timeline_events": timeline,
        "causal_timeline": causal_timeline,
        "trace_timeline": trace_timeline,
        "propagation_chain": build_propagation_chain(trace_timeline),
        "raw_excerpt": excerpt[:2200],
    }
