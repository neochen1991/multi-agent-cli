"""Evidence/Claim/Hypothesis typed objects."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """封装Evidence相关数据结构或服务能力。"""
    evidence_id: str = ""
    source: str = ""
    source_ref: str = ""
    category: str = "unknown"
    snippet: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Claim(BaseModel):
    """封装Claim相关数据结构或服务能力。"""
    claim_id: str = ""
    summary: str = ""
    owner_agent: str = ""
    evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Hypothesis(BaseModel):
    """封装Hypothesis相关数据结构或服务能力。"""
    hypothesis_id: str = ""
    statement: str = ""
    status: str = "open"
    supporting_claim_ids: List[str] = Field(default_factory=list)
    counter_claim_ids: List[str] = Field(default_factory=list)
    final_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    owner_team: Optional[str] = None

