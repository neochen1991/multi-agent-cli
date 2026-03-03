"""Typed models for runtime lineage records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


LineageRecordType = Literal["session", "event", "agent", "tool", "summary"]


class LineageRecord(BaseModel):
    """A single lineage row persisted as JSONL."""

    session_id: str
    trace_id: str = ""
    seq: int = 0
    kind: LineageRecordType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    phase: str = ""
    agent_name: str = ""
    event_type: str = ""
    confidence: float = 0.0
    duration_ms: float = 0.0
    input_summary: Dict[str, Any] = Field(default_factory=dict)
    output_summary: Dict[str, Any] = Field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)

