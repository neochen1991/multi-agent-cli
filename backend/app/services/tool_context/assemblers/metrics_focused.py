"""Metrics-focused context assembler."""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_metrics_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
    if not isinstance(tool_data, dict):
        tool_data = {}
    signals = [item for item in list(tool_data.get("signals") or []) if isinstance(item, dict)]
    causal_metric_chain = service._build_metric_causal_chain(signals[:16])  # noqa: SLF001
    return {
        "analysis_objective": {
            "task": str((assigned_command or {}).get("task") or "")[:240],
            "focus": str((assigned_command or {}).get("focus") or "")[:300],
        },
        "metric_signals": signals[:16],
        "metric_timeline_summary": service._summarize_metric_signals(signals[:16]),  # noqa: SLF001
        "causal_metric_chain": causal_metric_chain,
        "remote_sources": {
            "telemetry": service._remote_source_summary(tool_data.get("remote_telemetry")),  # noqa: SLF001
            "prometheus": service._remote_source_summary(tool_data.get("remote_prometheus")),  # noqa: SLF001
            "loki": service._remote_source_summary(tool_data.get("remote_loki")),  # noqa: SLF001
            "grafana": service._remote_source_summary(tool_data.get("remote_grafana")),  # noqa: SLF001
            "apm": service._remote_source_summary(tool_data.get("remote_apm")),  # noqa: SLF001
        },
    }
