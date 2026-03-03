"""
异步任务队列（Celery 可选）
Async Task Queue (Celery Optional)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

import structlog

from app.config import settings

logger = structlog.get_logger()


class AsyncTaskQueue:
    """默认使用进程内任务队列；可选接入 Celery"""

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self.celery_app = None

        if settings.USE_CELERY:
            try:
                from celery import Celery

                self.celery_app = Celery(
                    "sre_debate_tasks",
                    broker=settings.REDIS_URL,
                    backend=settings.REDIS_URL,
                )
            except Exception as e:
                logger.warning("celery_init_failed_fallback_to_local", error=str(e))

    def _now_iso(self) -> str:
        return datetime.utcnow().isoformat()

    def _sweep_stale_tasks(self) -> None:
        now = datetime.utcnow().timestamp()
        timeout_seconds = max(60, int(settings.DEBATE_TIMEOUT or 600))
        for task in self._tasks.values():
            status = str(task.get("status") or "")
            if status not in {"pending", "running"}:
                continue
            started_at = str(task.get("started_at") or task.get("created_at") or "")
            try:
                started_ts = datetime.fromisoformat(started_at).timestamp()
            except Exception:
                continue
            if (now - started_ts) <= (timeout_seconds + 30):
                continue
            task["status"] = "failed"
            task["error"] = "task timeout watchdog"
            task["updated_at"] = self._now_iso()

    def submit(self, coro_factory: Callable[[], Awaitable[Any]], timeout_seconds: int | None = None) -> str:
        task_id = f"tsk_{uuid.uuid4().hex[:12]}"
        self._sweep_stale_tasks()
        self._tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "created_at": self._now_iso(),
            "updated_at": self._now_iso(),
            "started_at": None,
            "timeout_seconds": int(timeout_seconds or max(60, int(settings.DEBATE_TIMEOUT or 600))),
            "result": None,
            "error": None,
        }

        async def _runner():
            self._tasks[task_id]["status"] = "running"
            self._tasks[task_id]["started_at"] = self._now_iso()
            self._tasks[task_id]["updated_at"] = self._now_iso()
            try:
                wait_timeout = max(30, int(self._tasks[task_id].get("timeout_seconds") or 600))
                result = await asyncio.wait_for(coro_factory(), timeout=wait_timeout)
                self._tasks[task_id]["status"] = "completed"
                self._tasks[task_id]["result"] = result
            except asyncio.TimeoutError:
                self._tasks[task_id]["status"] = "failed"
                self._tasks[task_id]["error"] = "task timeout"
            except Exception as e:
                self._tasks[task_id]["status"] = "failed"
                self._tasks[task_id]["error"] = str(e)
            finally:
                self._tasks[task_id]["updated_at"] = self._now_iso()

        asyncio.create_task(_runner())
        return task_id

    def get(self, task_id: str) -> Dict[str, Any]:
        self._sweep_stale_tasks()
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        return task


task_queue = AsyncTaskQueue()
