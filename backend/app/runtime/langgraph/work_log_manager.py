"""Work log context manager for prompt injection.

Collects key runtime events (command/tool/result/failure) from local
session event files and compacts them into a small context block.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings


class WorkLogManager:
    """Build compact work-log context from runtime event stream."""

    def __init__(self) -> None:
        root = Path(settings.LOCAL_STORE_DIR)
        self._events_dir = root / "runtime" / "events"
        self._events_dir.mkdir(parents=True, exist_ok=True)

    def _events_path(self, session_id: str) -> Path:
        return self._events_dir / f"{session_id}.jsonl"

    def _read_events(self, session_id: str) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        path = self._events_path(session_id)
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                text = str(line or "").strip()
                if not text:
                    continue
                payload = json.loads(text)
                if isinstance(payload, dict):
                    rows.append(payload)
        except Exception:
            return []
        return rows

    @staticmethod
    def _norm_dt(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.isoformat()
        except Exception:
            return text

    def build_context(self, session_id: str, *, limit: int = 16) -> Dict[str, Any]:
        rows = self._read_events(session_id)
        if not rows:
            return {"items": [], "summary": {"commands": 0, "tools": 0, "results": 0, "failures": 0}}

        commands: List[Dict[str, Any]] = []
        tools: List[Dict[str, Any]] = []
        results: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []

        for event in rows:
            event_type = str(event.get("type") or "").strip()
            agent_name = str(event.get("agent_name") or "").strip()
            timestamp = self._norm_dt(event.get("timestamp"))
            if event_type == "agent_command_issued":
                command = event.get("command") if isinstance(event.get("command"), dict) else {}
                commands.append(
                    {
                        "at": timestamp,
                        "type": "command",
                        "agent": agent_name,
                        "task": str(command.get("task") or "")[:200],
                        "focus": str(command.get("focus") or "")[:120],
                    }
                )
            elif event_type in {"agent_tool_context_prepared", "agent_tool_io"}:
                tools.append(
                    {
                        "at": timestamp,
                        "type": "tool",
                        "agent": agent_name,
                        "tool": str(event.get("tool_name") or "")[:80],
                        "status": str(event.get("status") or event.get("io_status") or "")[:40],
                        "action": str(event.get("io_action") or "")[:80],
                        "summary": str(event.get("summary") or "")[:180],
                    }
                )
            elif event_type in {"agent_round", "agent_chat_message"}:
                output_json = event.get("output_json") if isinstance(event.get("output_json"), dict) else {}
                evidence_chain = output_json.get("evidence_chain") if isinstance(output_json.get("evidence_chain"), list) else []
                evidence_refs: List[str] = []
                for item in evidence_chain[:3]:
                    if isinstance(item, dict):
                        ref = str(item.get("source_ref") or item.get("evidence_id") or "").strip()
                        if ref:
                            evidence_refs.append(ref[:80])
                results.append(
                    {
                        "at": timestamp,
                        "type": "result",
                        "agent": agent_name,
                        "conclusion": str(event.get("conclusion") or output_json.get("conclusion") or "")[:220],
                        "confidence": float(event.get("confidence") or output_json.get("confidence") or 0.0),
                        "evidence_refs": evidence_refs,
                    }
                )
            elif event_type in {"llm_call_timeout", "llm_call_failed", "agent_tool_context_failed"}:
                failures.append(
                    {
                        "at": timestamp,
                        "type": "failure",
                        "agent": agent_name,
                        "event": event_type,
                        "reason": str(event.get("reason") or event.get("error") or "")[:240],
                    }
                )

        merged = (commands + tools + results + failures)[-max(1, int(limit or 16)) :]
        merged.sort(key=lambda item: str(item.get("at") or ""))
        return {
            "items": merged,
            "summary": {
                "commands": len(commands),
                "tools": len(tools),
                "results": len(results),
                "failures": len(failures),
            },
        }


work_log_manager = WorkLogManager()


__all__ = ["WorkLogManager", "work_log_manager"]
