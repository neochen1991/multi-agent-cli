"""知识库领域模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KnowledgeEntryType(str, Enum):
    """知识条目类型。"""

    CASE = "case"
    RUNBOOK = "runbook"
    POSTMORTEM_TEMPLATE = "postmortem_template"


class CaseFields(BaseModel):
    """运维案例结构化字段。"""

    incident_type: str = ""
    symptoms: List[str] = Field(default_factory=list)
    root_cause: str = ""
    solution: str = ""
    fix_steps: List[str] = Field(default_factory=list)


class RunbookFields(BaseModel):
    """Runbook / SOP 结构化字段。"""

    applicable_scenarios: List[str] = Field(default_factory=list)
    prechecks: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    rollback_plan: List[str] = Field(default_factory=list)
    verification_steps: List[str] = Field(default_factory=list)


class PostmortemTemplateFields(BaseModel):
    """复盘模板结构化字段。"""

    impact_scope_template: List[str] = Field(default_factory=list)
    timeline_template: List[str] = Field(default_factory=list)
    five_whys_template: List[str] = Field(default_factory=list)
    action_items_template: List[str] = Field(default_factory=list)


class KnowledgeEntry(BaseModel):
    """统一知识条目。"""

    id: str
    entry_type: KnowledgeEntryType
    title: str
    summary: str = ""
    content: str = ""
    tags: List[str] = Field(default_factory=list)
    service_names: List[str] = Field(default_factory=list)
    domain: str = ""
    aggregate: str = ""
    author: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    case_fields: Optional[CaseFields] = None
    runbook_fields: Optional[RunbookFields] = None
    postmortem_fields: Optional[PostmortemTemplateFields] = None
