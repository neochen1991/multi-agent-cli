"""
Runtime task registry with local file persistence.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings


@dataclass
class TaskRecord:
    session_id: str
    task_type: str
    status: str
    started_at: str
    updated_at: str
    trace_id: str = ""
    error: str = ""
    last_phase: str = ""
    last_event_type: str = ""
    last_round: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_type": self.task_type,
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "trace_id": self.trace_id,
            "error": self.error,
            "last_phase": self.last_phase,
            "last_event_type": self.last_event_type,
            "last_round": self.last_round,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TaskRecord":
        return cls(
            session_id=str(payload.get("session_id") or ""),
            task_type=str(payload.get("task_type") or "debate"),
            status=str(payload.get("status") or "running"),
            started_at=str(payload.get("started_at") or datetime.utcnow().isoformat()),
            updated_at=str(payload.get("updated_at") or datetime.utcnow().isoformat()),
            trace_id=str(payload.get("trace_id") or ""),
            error=str(payload.get("error") or ""),
            last_phase=str(payload.get("last_phase") or ""),
            last_event_type=str(payload.get("last_event_type") or ""),
            last_round=int(payload.get("last_round") or 0),
        )


class RuntimeTaskRegistry:
    """Persisted task registry used for resume/recovery after reconnect/restart."""

    def __init__(self, base_dir: Optional[str] = None):
        root = Path(base_dir or settings.LOCAL_STORE_DIR) / "runtime"
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "tasks.json"
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, TaskRecord] = {}
        self._load_from_disk()

    async def mark_started(
        self,
        session_id: str,
        task_type: str = "debate",
        trace_id: str = "",
    ) -> TaskRecord:
        now = datetime.utcnow().isoformat()
        async with self._lock:
            record = TaskRecord(
                session_id=session_id,
                task_type=task_type,
                status="running",
                started_at=now,
                updated_at=now,
                trace_id=trace_id,
                last_phase="",
                last_event_type="",
                last_round=0,
            )
            self._tasks[session_id] = record
            self._persist_locked()
            return record

    async def mark_heartbeat(
        self,
        session_id: str,
        *,
        phase: str = "",
        event_type: str = "",
        round_number: int | None = None,
    ) -> Optional[TaskRecord]:
        async with self._lock:
            record = self._tasks.get(session_id)
            if not record:
                return None
            record.updated_at = datetime.utcnow().isoformat()
            if phase:
                record.last_phase = str(phase)
            if event_type:
                record.last_event_type = str(event_type)
            if round_number is not None:
                try:
                    record.last_round = max(0, int(round_number))
                except (TypeError, ValueError):
                    pass
            self._persist_locked()
            return record

    async def mark_done(self, session_id: str, status: str, error: str = "") -> Optional[TaskRecord]:
        async with self._lock:
            record = self._tasks.get(session_id)
            if not record:
                return None
            record.status = status
            record.error = error
            record.updated_at = datetime.utcnow().isoformat()
            self._persist_locked()
            return record

    async def get(self, session_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            self._sweep_stale_running_locked()
            record = self._tasks.get(session_id)
            return TaskRecord.from_dict(record.to_dict()) if record else None

    async def list_running(self) -> Dict[str, Dict[str, Any]]:
        async with self._lock:
            self._sweep_stale_running_locked()
            return {
                key: value.to_dict()
                for key, value in self._tasks.items()
                if value.status == "running"
            }

    async def sweep_stale_running(self, max_idle_seconds: int | None = None) -> int:
        async with self._lock:
            return self._sweep_stale_running_locked(max_idle_seconds=max_idle_seconds)

    def _sweep_stale_running_locked(self, max_idle_seconds: int | None = None) -> int:
        timeout_seconds = int(max_idle_seconds or max(60, int(settings.DEBATE_TIMEOUT or 600) + 30))
        now_ts = datetime.utcnow().timestamp()
        updated = 0
        for item in self._tasks.values():
            if str(item.status or "") != "running":
                continue
            checkpoint = str(item.updated_at or item.started_at or "")
            if not checkpoint:
                continue
            try:
                cp_ts = datetime.fromisoformat(checkpoint).timestamp()
            except Exception:
                continue
            if (now_ts - cp_ts) <= timeout_seconds:
                continue
            item.status = "failed"
            item.error = "runtime_task_watchdog_timeout"
            item.updated_at = datetime.utcnow().isoformat()
            updated += 1
        if updated > 0:
            self._persist_locked()
        return updated

    def _load_from_disk(self) -> None:
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return
            loaded: Dict[str, TaskRecord] = {}
            for key, value in payload.items():
                if not isinstance(value, dict):
                    continue
                item = TaskRecord.from_dict(value)
                if item.session_id:
                    loaded[item.session_id] = item
            self._tasks = loaded
        except Exception:
            self._tasks = {}

    def _persist_locked(self) -> None:
        payload = {key: value.to_dict() for key, value in self._tasks.items()}
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)


runtime_task_registry = RuntimeTaskRegistry()
