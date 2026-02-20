"""
统一事件模型
Unified Event Schema
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4


EVENT_SCHEMA_VERSION = "v1"


def new_trace_id(prefix: str = "trc") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def enrich_event(
    event: Dict[str, Any],
    trace_id: Optional[str] = None,
    default_phase: Optional[str] = None,
) -> Dict[str, Any]:
    payload = dict(event or {})
    payload.setdefault("event_id", f"evt_{uuid4().hex[:16]}")
    payload.setdefault("payload_version", EVENT_SCHEMA_VERSION)
    payload.setdefault("timestamp", datetime.utcnow().isoformat())
    payload.setdefault("trace_id", trace_id or new_trace_id())
    if default_phase and not payload.get("phase"):
        payload["phase"] = default_phase
    if payload.get("agent_name") and not payload.get("agent"):
        payload["agent"] = payload["agent_name"]
    return payload
