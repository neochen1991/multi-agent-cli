"""Derive propagation chain from aligned trace timeline."""

from __future__ import annotations

from typing import Any, Dict, List


def build_propagation_chain(trace_timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    chain: List[Dict[str, Any]] = []
    for item in trace_timeline:
        message = str(item.get("message") or "").lower()
        source = str(item.get("source") or "")
        stage = ""
        if source == "log" and ("uri=" in message or "/api/" in message):
            stage = "request_entry"
        elif "transaction" in message or "createorder" in message or source == "trace":
            stage = "application_processing"
        elif any(token in message for token in ("hikari", "connection", "lock", "pool")):
            stage = "resource_contention"
        elif any(token in message for token in ("502", "timeout", "5xx", "upstream")):
            stage = "user_visible_failure"
        if not stage:
            continue
        chain.append(
            {
                "stage": stage,
                "timestamp": str(item.get("timestamp") or ""),
                "service": str(item.get("service") or ""),
                "component": str(item.get("component") or ""),
                "message": str(item.get("message") or "")[:220],
                "source": source,
            }
        )
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in chain:
        key = f"{item.get('stage')}|{item.get('component')}|{item.get('timestamp')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:10]
