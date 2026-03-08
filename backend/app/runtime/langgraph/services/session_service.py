"""
会话服务模块

本模块提供 LangGraph 辩论运行时的会话生命周期管理。

核心功能：
1. 会话创建和初始化
2. 状态持久化和检索
3. 会话失败处理
4. 会话完成标记

会话生命周期：
created -> active -> completed/failed

使用场景：
- 运行时编排器管理会话状态
- 断点恢复时加载会话
- 故障处理时标记失败

Session service for LangGraph debate runtime.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


class SessionService:
    """
    会话生命周期管理服务

    提供会话的完整生命周期管理：
    - 创建：初始化会话元数据
    - 状态管理：保存和加载状态
    - 完成：标记成功或失败

    属性：
    - _sessions: 会话字典（session_id -> 会话数据）

    会话数据结构：
    {
        "session_id": "会话ID",
        "trace_id": "追踪ID",
        "context": "上下文数据",
        "created_at": "创建时间",
        "status": "状态（active/completed/failed）",
        "state": "运行时状态"
    }
    """

    def __init__(self) -> None:
        """
        初始化会话服务

        创建空的会话字典。
        """
        self._sessions: Dict[str, Dict[str, Any]] = {}

    async def create(
        self,
        session_id: str,
        trace_id: str,
        context: Dict[str, Any],
    ) -> None:
        """
        创建新会话

        初始化会话元数据和状态。

        Args:
            session_id: 唯一会话标识
            trace_id: 追踪 ID，用于日志关联
            context: 会话初始上下文
        """
        self._sessions[session_id] = {
            "session_id": session_id,
            "trace_id": trace_id,
            "context": context,
            "created_at": datetime.utcnow().isoformat(),
            "status": "active",
            "state": None,
        }

        logger.info(
            "session_created",
            session_id=session_id,
            trace_id=trace_id,
        )

    async def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话状态

        Args:
            session_id: 会话标识

        Returns:
            Optional[Dict[str, Any]]: 当前状态，不存在则返回 None
        """
        session = self._sessions.get(session_id)
        if session:
            return session.get("state")
        return None

    async def save_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """
        保存会话状态

        Args:
            session_id: 会话标识
            state: 要保存的状态
        """
        if session_id in self._sessions:
            self._sessions[session_id]["state"] = state
            self._sessions[session_id]["updated_at"] = datetime.utcnow().isoformat()

            logger.debug(
                "session_state_saved",
                session_id=session_id,
            )

    async def fail(self, session_id: str, reason: str = "") -> None:
        """
        标记会话失败

        Args:
            session_id: 会话标识
            reason: 失败原因
        """
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "failed"
            self._sessions[session_id]["failed_at"] = datetime.utcnow().isoformat()
            self._sessions[session_id]["failure_reason"] = reason

            logger.warning(
                "session_failed",
                session_id=session_id,
                reason=reason,
            )

    async def complete(self, session_id: str) -> None:
        """
        标记会话完成

        Args:
            session_id: 会话标识
        """
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "completed"
            self._sessions[session_id]["completed_at"] = datetime.utcnow().isoformat()

            logger.info(
                "session_completed",
                session_id=session_id,
            )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话元数据

        Args:
            session_id: 会话标识

        Returns:
            Optional[Dict[str, Any]]: 会话元数据，不存在则返回 None
        """
        return self._sessions.get(session_id)

    def has_session(self, session_id: str) -> bool:
        """
        检查会话是否存在

        Args:
            session_id: 会话标识

        Returns:
            bool: 是否存在
        """
        return session_id in self._sessions

    def clear_session(self, session_id: str) -> bool:
        """
        清理会话

        从内存中移除会话。

        Args:
            session_id: 会话标识

        Returns:
            bool: 是否成功清理
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False


__all__ = ["SessionService"]