"""
LangGraph runtime message contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentEvidence(BaseModel):
    """Standardized per-agent output contract."""

    agent_name: str
    phase: str
    summary: str = ""
    conclusion: str = ""
    evidence_chain: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_output: Dict[str, Any] = Field(default_factory=dict)


class RoundCheckpoint(BaseModel):
    """Persisted round-level checkpoint payload."""

    session_id: str
    round_number: int
    loop_round: int
    phase: str
    agent_name: str
    confidence: float
    summary: str
    conclusion: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FinalVerdict(BaseModel):
    """Normalized final verdict from JudgeAgent."""

    root_cause: Dict[str, Any] = Field(default_factory=dict)
    evidence_chain: List[Dict[str, Any]] = Field(default_factory=list)
    fix_recommendation: Dict[str, Any] = Field(default_factory=dict)
    impact_analysis: Dict[str, Any] = Field(default_factory=dict)
    risk_assessment: Dict[str, Any] = Field(default_factory=dict)


class RuntimeState(BaseModel):
    """Whole runtime state persisted on disk for resume/debug."""

    session_id: str
    trace_id: str
    status: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    context_summary: Dict[str, Any] = Field(default_factory=dict)
    rounds: List[RoundCheckpoint] = Field(default_factory=list)
    final_verdict: Optional[FinalVerdict] = None
