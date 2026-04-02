"""Runtime task registry with SQLite persistence."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from app.storage import SqliteStore, sqlite_store


@dataclass
class TaskRecord:
    """封装TaskRecord相关数据结构或服务能力。"""
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
    review_reason: str = ""
    resume_from_step: str = ""
    review_status: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """执行todict相关逻辑，并为当前模块提供可复用的处理能力。"""
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
            "review_reason": self.review_reason,
            "resume_from_step": self.resume_from_step,
            "review_status": self.review_status,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TaskRecord":
        """执行fromdict相关逻辑，并为当前模块提供可复用的处理能力。"""
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
            review_reason=str(payload.get("review_reason") or ""),
            resume_from_step=str(payload.get("resume_from_step") or ""),
            review_status=str(payload.get("review_status") or ""),
        )


class RuntimeTaskRegistry:
    """Persisted task registry used for resume/recovery after reconnect/restart."""

    def __init__(self, base_dir: Optional[str] = None):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        raw_path = Path(str(base_dir or getattr(settings, "LOCAL_STORE_SQLITE_PATH", "") or ""))
        store_path = str(raw_path / "app.db") if raw_path and raw_path.suffix == "" else str(raw_path)
        self._store: SqliteStore = sqlite_store if not store_path else SqliteStore(store_path)
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, TaskRecord] = {}
        self._load_from_sqlite()

    async def mark_started(
        self,
        session_id: str,
        task_type: str = "debate",
        trace_id: str = "",
    ) -> TaskRecord:
        """执行markstarted相关逻辑，并为当前模块提供可复用的处理能力。"""
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
            await self._persist_locked()
            return record

    async def mark_heartbeat(
        self,
        session_id: str,
        *,
        phase: str = "",
        event_type: str = "",
        round_number: int | None = None,
    ) -> Optional[TaskRecord]:
        """执行markheartbeat相关逻辑，并为当前模块提供可复用的处理能力。"""
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
            await self._persist_locked()
            return record

    async def mark_done(self, session_id: str, status: str, error: str = "") -> Optional[TaskRecord]:
        """执行markdone相关逻辑，并为当前模块提供可复用的处理能力。"""
        async with self._lock:
            record = self._tasks.get(session_id)
            if not record:
                return None
            record.status = status
            record.error = error
            record.updated_at = datetime.utcnow().isoformat()
            await self._persist_locked()
            return record

    async def mark_waiting_review(
        self,
        session_id: str,
        *,
        review_reason: str = "",
        resume_from_step: str = "",
        phase: str = "",
        event_type: str = "",
        round_number: int | None = None,
    ) -> Optional[TaskRecord]:
        """执行markwaiting审核相关逻辑，并为当前模块提供可复用的处理能力。"""
        async with self._lock:
            record = self._tasks.get(session_id)
            if not record:
                return None
            record.status = "waiting_review"
            record.review_reason = str(review_reason or "")
            record.resume_from_step = str(resume_from_step or "")
            record.review_status = "pending"
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
            await self._persist_locked()
            return record

    async def mark_review_decision(
        self,
        session_id: str,
        *,
        review_status: str,
        status: str | None = None,
        error: str = "",
    ) -> Optional[TaskRecord]:
        """执行mark审核decision相关逻辑，并为当前模块提供可复用的处理能力。"""
        async with self._lock:
            record = self._tasks.get(session_id)
            if not record:
                return None
            record.review_status = str(review_status or "")
            if status:
                record.status = str(status)
            if error:
                record.error = str(error)
            record.updated_at = datetime.utcnow().isoformat()
            await self._persist_locked()
            return record

    async def get(self, session_id: str) -> Optional[TaskRecord]:
        """负责获取，并返回后续流程可直接消费的数据结果。"""
        async with self._lock:
            updated = self._sweep_stale_running_locked()
            if updated > 0:
                await self._persist_locked()
            record = self._tasks.get(session_id)
            return TaskRecord.from_dict(record.to_dict()) if record else None

    async def list_running(self) -> Dict[str, Dict[str, Any]]:
        """负责列出running，并返回后续流程可直接消费的数据结果。"""
        async with self._lock:
            updated = self._sweep_stale_running_locked()
            if updated > 0:
                await self._persist_locked()
            return {
                key: value.to_dict()
                for key, value in self._tasks.items()
                if value.status == "running"
            }

    async def sweep_stale_running(self, max_idle_seconds: int | None = None) -> int:
        """执行sweepstalerunning相关逻辑，并为当前模块提供可复用的处理能力。"""
        async with self._lock:
            updated = self._sweep_stale_running_locked(max_idle_seconds=max_idle_seconds)
            if updated > 0:
                await self._persist_locked()
            return updated

    def _sweep_stale_running_locked(self, max_idle_seconds: int | None = None) -> int:
        """执行sweepstalerunninglocked相关逻辑，并为当前模块提供可复用的处理能力。"""
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
        return updated

    def _load_from_sqlite(self) -> None:
        """从 SQLite 预加载任务记录。"""
        try:
            conn = sqlite3.connect(str(self._store.db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT payload_json FROM runtime_tasks ORDER BY updated_at DESC"
                ).fetchall()
            finally:
                conn.close()
            loaded: Dict[str, TaskRecord] = {}
            for row in rows:
                value = self._store.loads_json(row["payload_json"], {})
                if not isinstance(value, dict):
                    continue
                item = TaskRecord.from_dict(value)
                if item.session_id:
                    loaded[item.session_id] = item
            self._tasks = loaded
        except Exception:
            self._tasks = {}

    async def _persist_locked(self) -> None:
        """把任务快照写入 runtime_tasks 表。"""
        await self._store.execute("DELETE FROM runtime_tasks")
        rows = [
            (
                key,
                value.updated_at,
                self._store.dumps_json(value.to_dict()),
            )
            for key, value in self._tasks.items()
        ]
        if rows:
            await self._store.executemany(
                """
                INSERT INTO runtime_tasks (session_id, updated_at, payload_json)
                VALUES (?, ?, ?)
                """,
                rows,
            )


runtime_task_registry = RuntimeTaskRegistry()
