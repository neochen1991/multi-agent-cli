"""Shared result model for tool-context providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ToolContextResult:
    """统一的工具上下文返回结构，供 runtime、前端和审计链复用。"""

    name: str
    enabled: bool
    used: bool
    status: str
    summary: str
    data: Dict[str, Any]
    command_gate: Dict[str, Any] = field(default_factory=dict)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    execution_path: str = ""
    permission_decision: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "used": self.used,
            "status": self.status,
            "summary": self.summary,
            "data": self.data,
            "command_gate": self.command_gate,
            "audit_log": self.audit_log,
            "execution_path": self.execution_path,
            "permission_decision": self.permission_decision,
        }
