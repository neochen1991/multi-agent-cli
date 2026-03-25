"""Audit helpers for tool/skill context execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Dict, List, Optional


@dataclass
class ToolAuditBuilder:
    """Build normalized audit entries with stable call IDs."""

    sequence: int = 0

    def command_preview(self, assigned_command: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        command = dict(assigned_command or {})
        skill_hints_raw = command.get("skill_hints")
        skill_hints = (
            [str(item or "").strip()[:80] for item in skill_hints_raw if str(item or "").strip()]
            if isinstance(skill_hints_raw, list)
            else []
        )
        tool_hints_raw = command.get("tool_hints")
        tool_hints = (
            [str(item or "").strip()[:80] for item in tool_hints_raw if str(item or "").strip()]
            if isinstance(tool_hints_raw, list)
            else []
        )
        return {
            "task": str(command.get("task") or "")[:240],
            "focus": str(command.get("focus") or "")[:240],
            "expected_output": str(command.get("expected_output") or "")[:240],
            "use_tool": command.get("use_tool"),
            "skill_hints": skill_hints[:8],
            "tool_hints": tool_hints[:8],
        }

    def build_entry(
        self,
        *,
        tool_name: str,
        action: str,
        status: str,
        detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        detail_payload = detail if isinstance(detail, dict) else {"value": str(detail or "")}
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "call_id": self.next_call_id(tool_name=tool_name, action=action),
            "tool_name": tool_name,
            "action": action,
            "status": status,
            "request_summary": self._request_summary(detail_payload),
            "response_summary": self._response_summary(detail_payload),
            "detail_preview": self._detail_preview(detail_payload),
            "duration_ms": self._coerce_duration_ms(detail_payload),
            "detail": detail_payload,
        }

    def next_call_id(self, *, tool_name: str, action: str) -> str:
        self.sequence += 1
        tool = re.sub(r"[^a-z0-9]+", "_", str(tool_name or "tool").lower()).strip("_") or "tool"
        act = re.sub(r"[^a-z0-9]+", "_", str(action or "action").lower()).strip("_") or "action"
        return f"{tool}_{act}_{self.sequence:06d}"

    @staticmethod
    def _detail_preview(detail: Dict[str, Any], *, max_chars: int = 420) -> str:
        try:
            text = json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = str(detail)
        text = str(text or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}..."

    @staticmethod
    def _request_summary(detail: Dict[str, Any]) -> str:
        picks: List[str] = []
        for key in ("path", "repo_url", "endpoint", "sheet_name", "keywords", "query", "service_name"):
            value = detail.get(key)
            if value in (None, "", [], {}):
                continue
            picks.append(f"{key}={str(value)[:100]}")
        return "；".join(picks)[:260]

    @staticmethod
    def _response_summary(detail: Dict[str, Any]) -> str:
        picks: List[str] = []
        for key in ("status", "hits_count", "lines_count", "matches_count", "match_count", "result_count", "error"):
            value = detail.get(key)
            if value in (None, "", [], {}):
                continue
            picks.append(f"{key}={str(value)[:100]}")
        return "；".join(picks)[:260]

    @staticmethod
    def _coerce_duration_ms(detail: Dict[str, Any]) -> Optional[float]:
        for key in ("duration_ms", "latency_ms", "elapsed_ms"):
            value = detail.get(key)
            if value is None:
                continue
            try:
                return round(float(value), 2)
            except Exception:
                continue
        return None
