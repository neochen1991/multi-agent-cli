"""Work log context manager for prompt injection.

Collects key runtime events (command/tool/result/failure) from local
session event files and compacts them into a small context block.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from app.storage import sqlite_store


class WorkLogManager:
    """Build compact work-log context from runtime event stream."""

    def __init__(self) -> None:
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._store = sqlite_store

    def _read_events(self, session_id: str) -> List[Dict[str, Any]]:
        """负责读取events，并返回后续流程可直接消费的数据结果。"""
        if not session_id:
            return []
        try:
            conn = sqlite3.connect(str(self._store.db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT payload_json FROM runtime_events
                    WHERE session_id = ?
                    ORDER BY id ASC
                    """,
                    (session_id,),
                ).fetchall()
            finally:
                conn.close()
            return [self._store.loads_json(row["payload_json"], {}) for row in rows]
        except Exception:
            return []

    @staticmethod
    def _norm_dt(value: Any) -> str:
        """执行normdt相关逻辑，并为当前模块提供可复用的处理能力。"""
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.isoformat()
        except Exception:
            return text

    def build_context(self, session_id: str, *, limit: int = 16) -> Dict[str, Any]:
        """构建构建上下文，供后续节点或调用方直接使用。"""
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
