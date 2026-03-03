"""Models for tool registry records."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ToolPolicy(BaseModel):
    timeout_seconds: int = 30
    audit_level: str = "full"
    command_whitelist: List[str] = Field(default_factory=list)
    path_whitelist: List[str] = Field(default_factory=list)
    redact_fields: List[str] = Field(default_factory=lambda: ["access_token", "api_key", "password"])


class ToolRegistryItem(BaseModel):
    tool_name: str
    category: str
    owner_agent: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    policy: ToolPolicy = Field(default_factory=ToolPolicy)
