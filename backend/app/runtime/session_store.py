"""
运行时会话检查点存储模块

本模块提供运行时状态的持久化存储，支持断点恢复。

核心功能：
1. 会话状态持久化（RuntimeState）
2. 事件流追加存储
3. 回合检查点记录
4. 最终裁决结果存储

存储结构：
- SQLite.runtime_sessions - 会话状态
- SQLite.runtime_events - 事件流

使用场景：
- 断点恢复：从 SQLite 加载之前的执行状态
- 事件回放：按时间顺序读取事件流
- 状态同步：多进程间共享执行状态

Local runtime session checkpoint store.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from app.config import settings
from app.runtime.messages import RuntimeState, RoundCheckpoint, FinalVerdict
from app.storage import SqliteStore, sqlite_store


class RuntimeSessionStore:
    """
    基于 SQLite 的运行时检查点/事件存储

    属性：
    - _store: SQLite 结构化存储
    - _lock: 异步锁，保证并发安全

    状态生命周期：
    running -> waiting_review -> completed/failed
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化运行时会话存储

        Args:
            base_dir: 兼容旧调用方保留，当前不再用于文件落盘
        """
        store_path = str(base_dir or getattr(settings, "LOCAL_STORE_SQLITE_PATH", "") or "")
        self._store: SqliteStore = sqlite_store if not store_path else SqliteStore(store_path)
        self._lock = asyncio.Lock()

    async def create(
        self,
        session_id: str,
        trace_id: str,
        context_summary: Dict[str, Any],
    ) -> RuntimeState:
        """
        创建运行时状态

        初始化一个新的运行时会话状态。

        Args:
            session_id: 会话 ID
            trace_id: 追踪 ID
            context_summary: 上下文摘要

        Returns:
            RuntimeState: 创建的状态对象
        """
        state = RuntimeState(
            session_id=session_id,
            trace_id=trace_id,
            status="running",
            context_summary=context_summary,
        )
        await self._save_state(state)
        return state

    async def load(self, session_id: str) -> Optional[RuntimeState]:
        """
        加载运行时状态

        从 SQLite 读取会话状态，用于断点恢复。

        Args:
            session_id: 会话 ID

        Returns:
            Optional[RuntimeState]: 状态对象，不存在则返回 None
        """
        async with self._lock:
            row = await self._store.fetchone(
                "SELECT payload_json FROM runtime_sessions WHERE session_id = ?",
                (session_id,),
            )
            if row is None:
                return None
            return RuntimeState.model_validate(self._store.loads_json(row["payload_json"], {}))

    async def append_round(self, session_id: str, checkpoint: RoundCheckpoint) -> None:
        """
        追加回合检查点

        记录一个 Agent 执行回合的检查点。

        Args:
            session_id: 会话 ID
            checkpoint: 回合检查点数据
        """
        async with self._lock:
            state = await self._load_state_locked(session_id)
            if not state:
                return
            state.rounds.append(checkpoint)
            state.updated_at = datetime.utcnow()
            await self._save_state_locked(state)

    async def complete(self, session_id: str, verdict: FinalVerdict) -> None:
        """
        标记会话完成

        将会话状态设为 completed，并记录最终裁决。

        Args:
            session_id: 会话 ID
            verdict: 最终裁决结果
        """
        async with self._lock:
            state = await self._load_state_locked(session_id)
            if not state:
                return
            state.final_verdict = verdict
            state.status = "completed"
            state.updated_at = datetime.utcnow()
            await self._save_state_locked(state)

    async def mark_waiting_review(self, session_id: str, verdict: FinalVerdict) -> None:
        """
        标记等待人工审核

        将会话状态设为 waiting_review，暂停执行等待人工确认。

        Args:
            session_id: 会话 ID
            verdict: 待审核的裁决结果
        """
        async with self._lock:
            state = await self._load_state_locked(session_id)
            if not state:
                return
            state.final_verdict = verdict
            state.status = "waiting_review"
            state.updated_at = datetime.utcnow()
            await self._save_state_locked(state)

    async def fail(self, session_id: str) -> None:
        """
        标记会话失败

        将会话状态设为 failed。

        Args:
            session_id: 会话 ID
        """
        async with self._lock:
            state = await self._load_state_locked(session_id)
            if not state:
                return
            state.status = "failed"
            state.updated_at = datetime.utcnow()
            await self._save_state_locked(state)

    async def append_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """
        追加事件

        将事件追加到运行时事件表。

        Args:
            session_id: 会话 ID
            event: 事件数据字典
        """
        async with self._lock:
            payload = dict(event or {})
            await self._store.execute(
                """
                INSERT INTO runtime_events (session_id, event_type, agent_name, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    str(payload.get("type") or ""),
                    str(payload.get("agent_name") or ""),
                    str(payload.get("timestamp") or datetime.utcnow().isoformat()),
                    self._store.dumps_json(payload),
                ),
            )

    async def list_events(self, session_id: str) -> list[Dict[str, Any]]:
        """按写入顺序返回指定会话的运行时事件。"""
        async with self._lock:
            rows = await self._store.fetchall(
                """
                SELECT payload_json FROM runtime_events
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            )
            return [self._store.loads_json(row["payload_json"], {}) for row in rows]

    async def _save_state(self, state: RuntimeState) -> None:
        """
        保存状态（带锁）

        Args:
            state: 运行时状态
        """
        async with self._lock:
            await self._save_state_locked(state)

    async def _load_state_locked(self, session_id: str) -> Optional[RuntimeState]:
        """
        加载状态（已持有锁）

        内部方法，调用前需已获取锁。

        Args:
            session_id: 会话 ID

        Returns:
            Optional[RuntimeState]: 状态对象
        """
        row = await self._store.fetchone(
            "SELECT payload_json FROM runtime_sessions WHERE session_id = ?",
            (session_id,),
        )
        if row is None:
            return None
        return RuntimeState.model_validate(self._store.loads_json(row["payload_json"], {}))

    async def _save_state_locked(self, state: RuntimeState) -> None:
        """
        保存状态（已持有锁）

        Args:
            state: 运行时状态
        """
        payload = state.model_dump(mode="json")
        await self._store.execute(
            """
            INSERT OR REPLACE INTO runtime_sessions
            (session_id, trace_id, status, updated_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                state.session_id,
                state.trace_id,
                state.status,
                str(payload.get("updated_at") or datetime.utcnow().isoformat()),
                self._store.dumps_json(payload),
            ),
        )

# 全局实例
runtime_session_store = RuntimeSessionStore()
