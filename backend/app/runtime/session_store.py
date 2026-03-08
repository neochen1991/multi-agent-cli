"""
运行时会话检查点存储模块

本模块提供运行时状态的持久化存储，支持断点恢复。

核心功能：
1. 会话状态持久化（RuntimeState）
2. 事件流追加存储
3. 回合检查点记录
4. 最终裁决结果存储

存储结构：
- {LOCAL_STORE_DIR}/runtime/sessions/{session_id}.json - 会话状态
- {LOCAL_STORE_DIR}/runtime/events/{session_id}.jsonl - 事件流

使用场景：
- 断点恢复：从磁盘加载之前的执行状态
- 事件回放：按时间顺序读取事件流
- 状态同步：多进程间共享执行状态

Local runtime session checkpoint store.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from app.runtime.messages import RuntimeState, RoundCheckpoint, FinalVerdict


class RuntimeSessionStore:
    """
    基于文件的运行时检查点/事件存储

    无需外部数据库，使用本地文件系统持久化：
    - 会话状态：JSON 格式，原子写入
    - 事件流：JSONL 格式，追加写入

    属性：
    - _root: 运行时存储根目录
    - _state_dir: 会话状态目录
    - _events_dir: 事件流目录
    - _lock: 异步锁，保证并发安全

    状态生命周期：
    running -> waiting_review -> completed/failed
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化运行时会话存储

        创建存储目录结构：
        - {base_dir}/runtime/sessions/ - 会话状态
        - {base_dir}/runtime/events/ - 事件流

        Args:
            base_dir: 基础存储目录，未提供则使用配置值
        """
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        self._root = root / "runtime"
        self._state_dir = self._root / "sessions"
        self._events_dir = self._root / "events"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._events_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _state_path(self, session_id: str) -> Path:
        """
        获取会话状态文件路径

        Args:
            session_id: 会话 ID

        Returns:
            Path: 状态文件路径
        """
        return self._state_dir / f"{session_id}.json"

    def _events_path(self, session_id: str) -> Path:
        """
        获取事件流文件路径

        Args:
            session_id: 会话 ID

        Returns:
            Path: 事件流文件路径
        """
        return self._events_dir / f"{session_id}.jsonl"

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

        从磁盘读取会话状态，用于断点恢复。

        Args:
            session_id: 会话 ID

        Returns:
            Optional[RuntimeState]: 状态对象，不存在则返回 None
        """
        async with self._lock:
            path = self._state_path(session_id)
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            return RuntimeState.model_validate(payload)

    async def append_round(self, session_id: str, checkpoint: RoundCheckpoint) -> None:
        """
        追加回合检查点

        记录一个 Agent 执行回合的检查点。

        Args:
            session_id: 会话 ID
            checkpoint: 回合检查点数据
        """
        async with self._lock:
            state = self._load_state_locked(session_id)
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
            state = self._load_state_locked(session_id)
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
            state = self._load_state_locked(session_id)
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
            state = self._load_state_locked(session_id)
            if not state:
                return
            state.status = "failed"
            state.updated_at = datetime.utcnow()
            await self._save_state_locked(state)

    async def append_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """
        追加事件

        将事件追加到事件流文件（JSONL 格式）。

        Args:
            session_id: 会话 ID
            event: 事件数据字典
        """
        async with self._lock:
            path = self._events_path(session_id)
            line = json.dumps(event, ensure_ascii=False, default=str)
            with path.open("a", encoding="utf-8") as fp:
                fp.write(line)
                fp.write("\n")

    async def _save_state(self, state: RuntimeState) -> None:
        """
        保存状态（带锁）

        Args:
            state: 运行时状态
        """
        async with self._lock:
            await self._save_state_locked(state)

    def _load_state_locked(self, session_id: str) -> Optional[RuntimeState]:
        """
        加载状态（已持有锁）

        内部方法，调用前需已获取锁。

        Args:
            session_id: 会话 ID

        Returns:
            Optional[RuntimeState]: 状态对象
        """
        path = self._state_path(session_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeState.model_validate(payload)

    async def _save_state_locked(self, state: RuntimeState) -> None:
        """
        保存状态（已持有锁）

        使用临时文件原子写入，避免进程中断导致数据损坏。

        Args:
            state: 运行时状态
        """
        path = self._state_path(state.session_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)


# 全局实例
runtime_session_store = RuntimeSessionStore()