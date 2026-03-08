"""
异步任务队列模块

本模块提供异步任务执行功能，支持进程内队列和 Celery。

任务队列设计：
1. 默认使用进程内队列（适合单机部署）
2. 可选接入 Celery（适合分布式部署）
3. 支持任务超时和状态追踪

任务生命周期：
pending -> running -> completed/failed

使用场景：
- 辩论执行任务
- 报告生成任务
- 长时间运行的分析任务

核心组件：
- AsyncTaskQueue: 任务队列实现
- task_queue: 全局任务队列实例

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
    """
    异步任务队列

    支持进程内队列和 Celery 两种模式。

    进程内模式：
    - 使用 asyncio 创建后台任务
    - 任务状态存储在内存中
    - 适合单机部署

    Celery 模式：
    - 使用 Redis 作为消息代理
    - 支持分布式任务执行
    - 适合大规模部署

    属性：
    - _tasks: 任务状态存储
    - celery_app: Celery 应用实例（可选）

    任务状态：
    - pending: 等待执行
    - running: 正在执行
    - completed: 执行完成
    - failed: 执行失败
    """

    def __init__(self):
        """
        初始化任务队列

        根据配置选择队列模式。
        """
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self.celery_app = None

        # 如果配置使用 Celery，尝试初始化
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
        """
        获取当前时间的 ISO 格式字符串

        Returns:
            str: ISO 格式时间字符串
        """
        return datetime.utcnow().isoformat()

    def _sweep_stale_tasks(self) -> None:
        """
        清理过期任务

        检查所有运行中/等待中的任务，将超时任务标记为失败。
        防止任务状态泄漏。
        """
        now = datetime.utcnow().timestamp()
        timeout_seconds = max(60, int(settings.DEBATE_TIMEOUT or 600))

        for task in self._tasks.values():
            status = str(task.get("status") or "")
            if status not in {"pending", "running"}:
                continue

            # 获取任务开始时间
            started_at = str(task.get("started_at") or task.get("created_at") or "")
            try:
                started_ts = datetime.fromisoformat(started_at).timestamp()
            except Exception:
                continue

            # 检查是否超时
            if (now - started_ts) <= (timeout_seconds + 30):
                continue

            # 标记为超时失败
            task["status"] = "failed"
            task["error"] = "task timeout watchdog"
            task["updated_at"] = self._now_iso()

    def submit(self, coro_factory: Callable[[], Awaitable[Any]], timeout_seconds: int | None = None) -> str:
        """
        提交任务

        创建并启动一个异步任务。

        Args:
            coro_factory: 返回协程的工厂函数
            timeout_seconds: 任务超时时间（秒）

        Returns:
            str: 任务 ID
        """
        # 生成任务 ID
        task_id = f"tsk_{uuid.uuid4().hex[:12]}"

        # 清理过期任务
        self._sweep_stale_tasks()

        # 创建任务记录
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
            """
            任务执行器

            在后台执行任务并更新状态。
            """
            # 更新状态为运行中
            self._tasks[task_id]["status"] = "running"
            self._tasks[task_id]["started_at"] = self._now_iso()
            self._tasks[task_id]["updated_at"] = self._now_iso()

            try:
                # 执行任务，带超时控制
                wait_timeout = max(30, int(self._tasks[task_id].get("timeout_seconds") or 600))
                result = await asyncio.wait_for(coro_factory(), timeout=wait_timeout)

                # 标记完成
                self._tasks[task_id]["status"] = "completed"
                self._tasks[task_id]["result"] = result

            except asyncio.TimeoutError:
                # 超时失败
                self._tasks[task_id]["status"] = "failed"
                self._tasks[task_id]["error"] = "task timeout"

            except Exception as e:
                # 异常失败
                self._tasks[task_id]["status"] = "failed"
                self._tasks[task_id]["error"] = str(e)

            finally:
                self._tasks[task_id]["updated_at"] = self._now_iso()

        # 创建后台任务
        asyncio.create_task(_runner())
        return task_id

    def get(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            Dict[str, Any]: 任务状态字典

        Raises:
            KeyError: 任务不存在
        """
        self._sweep_stale_tasks()
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        return task


# 全局任务队列实例
task_queue = AsyncTaskQueue()