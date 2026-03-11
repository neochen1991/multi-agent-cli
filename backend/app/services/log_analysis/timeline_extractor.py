"""Build aligned trace timeline from log events and telemetry hints."""

from __future__ import annotations

from typing import Any, Dict, List


def build_trace_timeline(
    *,
    timeline_events: List[Dict[str, Any]],
    trace_id: str,
    service_name: str,
    tool_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    aligned: List[Dict[str, Any]] = []
    for item in timeline_events:
        aligned.append(
            {
                "timestamp": str(item.get("timestamp") or ""),
                "component": str(item.get("component") or service_name or ""),
                "service": str(service_name or item.get("component") or ""),
                "trace_id": trace_id,
                "message": str(item.get("message") or "")[:220],
                "source": "log",
            }
        )
    remote_telemetry = tool_data.get("remote_telemetry") if isinstance(tool_data.get("remote_telemetry"), dict) else {}
    payload = remote_telemetry.get("payload") if isinstance(remote_telemetry, dict) else {}
    for span in list(payload.get("spans") or [])[:6] if isinstance(payload, dict) else []:
        if not isinstance(span, dict):
            continue
        aligned.append(
            {
                "timestamp": str(span.get("timestamp") or ""),
                "component": str(span.get("span") or span.get("component") or service_name),
                "service": str(span.get("service") or service_name),
                "trace_id": trace_id,
                "message": str(span.get("summary") or span.get("name") or "")[:220],
                "source": "trace",
            }
        )
    remote_prometheus = tool_data.get("remote_prometheus") if isinstance(tool_data.get("remote_prometheus"), dict) else {}
    prom_payload = remote_prometheus.get("payload") if isinstance(remote_prometheus, dict) else {}
    for signal in list(prom_payload.get("signals") or [])[:4] if isinstance(prom_payload, dict) else []:
        if not isinstance(signal, dict):
            continue
        aligned.append(
            {
                "timestamp": str(signal.get("timestamp") or ""),
                "component": str(signal.get("metric") or "metric"),
                "service": str(service_name or ""),
                "trace_id": trace_id,
                "message": str(signal.get("summary") or signal.get("value") or "")[:220],
                "source": "metric",
            }
        )
    return aligned[:16]
