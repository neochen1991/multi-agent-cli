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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_type": self.task_type,
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "trace_id": self.trace_id,
            "error": self.error,
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
            )
            self._tasks[session_id] = record
            self._persist_locked()
            return record

    async def mark_heartbeat(self, session_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            record = self._tasks.get(session_id)
            if not record:
                return None
            record.updated_at = datetime.utcnow().isoformat()
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
            record = self._tasks.get(session_id)
            return TaskRecord.from_dict(record.to_dict()) if record else None

    async def list_running(self) -> Dict[str, Dict[str, Any]]:
        async with self._lock:
            return {
                key: value.to_dict()
                for key, value in self._tasks.items()
                if value.status == "running"
            }

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

