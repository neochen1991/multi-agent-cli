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
from zoneinfo import ZoneInfo


EVENT_SCHEMA_VERSION = "v1"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def new_trace_id(prefix: str = "trc") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _build_stable_event_id(payload: Dict[str, Any]) -> str:
    """Build a stable event id from key fields.

    For the same payload object, this returns the same id, which keeps
    websocket and persisted event entries aligned.
    """
    # Prefer deterministic identity by session + event_sequence.
    # Timestamp is excluded from the primary seed to keep ID stable
    # across replay/broadcast paths for the same logical event.
    seed = {
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
        "chunk_total": payload.get("chunk_total"),
    }
    if not payload.get("event_sequence"):
        seed["timestamp"] = payload.get("timestamp")
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return f"evt_{digest}"


def build_event_dedupe_key(payload: Dict[str, Any]) -> str:
    """Build a client-facing dedupe key for event stream rendering."""
    session_id = str(payload.get("session_id") or "").strip()
    event_sequence = str(payload.get("event_sequence") or "").strip()
    event_type = str(payload.get("type") or "").strip()
    stream_id = str(payload.get("stream_id") or "").strip()
    chunk_index = str(payload.get("chunk_index") or "").strip()
    phase = str(payload.get("phase") or "").strip()
    agent_name = str(payload.get("agent_name") or payload.get("agent") or "").strip()
    if session_id and event_sequence:
        base = f"{session_id}:{event_sequence}:{event_type}"
        if stream_id:
            base = f"{base}:{stream_id}:{chunk_index or '-'}"
        return base
    return f"{event_type}:{phase}:{agent_name}:{stream_id}:{chunk_index}"


def enrich_event(
    event: Dict[str, Any],
    trace_id: Optional[str] = None,
    default_phase: Optional[str] = None,
) -> Dict[str, Any]:
    payload = dict(event or {})
    payload.setdefault("timestamp", datetime.utcnow().isoformat())
    payload.setdefault("timestamp_bj", datetime.now(BEIJING_TZ).isoformat())
    payload.setdefault("payload_version", EVENT_SCHEMA_VERSION)
    payload.setdefault("trace_id", trace_id or new_trace_id())
    payload.setdefault("event_id", _build_stable_event_id(payload))
    payload.setdefault("dedupe_key", build_event_dedupe_key(payload))
    if default_phase and not payload.get("phase"):
        payload["phase"] = default_phase
    if payload.get("agent_name") and not payload.get("agent"):
        payload["agent"] = payload["agent_name"]
    return payload
