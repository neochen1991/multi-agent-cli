"""
统一事件模型
Unified Event Schema
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4


EVENT_SCHEMA_VERSION = "v1"


def new_trace_id(prefix: str = "trc") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _build_stable_event_id(payload: Dict[str, Any]) -> str:
    """Build a stable event id from key fields.

    For the same payload object, this returns the same id, which keeps
    websocket and persisted event entries aligned.
    """
    seed = {
        "timestamp": payload.get("timestamp"),
        "type": payload.get("type"),
        "phase": payload.get("phase"),
        "session_id": payload.get("session_id"),
        "trace_id": payload.get("trace_id"),
        "agent_name": payload.get("agent_name"),
        "round_number": payload.get("round_number"),
        "loop_round": payload.get("loop_round"),
        "event_sequence": payload.get("event_sequence"),
        "stream_id": payload.get("stream_id"),
        "chunk_index": payload.get("chunk_index"),
    }
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return f"evt_{digest}"


def enrich_event(
    event: Dict[str, Any],
    trace_id: Optional[str] = None,
    default_phase: Optional[str] = None,
) -> Dict[str, Any]:
    payload = dict(event or {})
    payload.setdefault("timestamp", datetime.utcnow().isoformat())
    payload.setdefault("payload_version", EVENT_SCHEMA_VERSION)
    payload.setdefault("trace_id", trace_id or new_trace_id())
    payload.setdefault("event_id", _build_stable_event_id(payload))
    if default_phase and not payload.get("phase"):
        payload["phase"] = default_phase
    if payload.get("agent_name") and not payload.get("agent"):
        payload["agent"] = payload["agent_name"]
    return payload
