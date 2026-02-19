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

    def submit(self, coro_factory: Callable[[], Awaitable[Any]]) -> str:
        task_id = f"tsk_{uuid.uuid4().hex[:12]}"
        self._tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "result": None,
            "error": None,
        }

        async def _runner():
            self._tasks[task_id]["status"] = "running"
            self._tasks[task_id]["updated_at"] = datetime.utcnow().isoformat()
            try:
                result = await coro_factory()
                self._tasks[task_id]["status"] = "completed"
                self._tasks[task_id]["result"] = result
            except Exception as e:
                self._tasks[task_id]["status"] = "failed"
                self._tasks[task_id]["error"] = str(e)
            finally:
                self._tasks[task_id]["updated_at"] = datetime.utcnow().isoformat()

        asyncio.create_task(_runner())
        return task_id

    def get(self, task_id: str) -> Dict[str, Any]:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        return task


task_queue = AsyncTaskQueue()

