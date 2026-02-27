"""Session service for LangGraph debate runtime.

This module provides session lifecycle management, including
creation, state persistence, and failure handling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


class SessionService:
    """Session lifecycle management.

    This service handles:
    - Session creation and initialization
    - State persistence and retrieval
    - Session failure handling
    """

    def __init__(self) -> None:
        """Initialize the session service."""
        self._sessions: Dict[str, Dict[str, Any]] = {}

    async def create(
        self,
        session_id: str,
        trace_id: str,
        context: Dict[str, Any],
    ) -> None:
        """Create a new session.

        Args:
            session_id: Unique session identifier.
            trace_id: Trace ID for correlation.
            context: Initial context for the session.
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
        """Get the current state for a session.

        Args:
            session_id: The session identifier.

        Returns:
            The current state, or None if not found.
        """
        session = self._sessions.get(session_id)
        if session:
            return session.get("state")
        return None

    async def save_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Save state for a session.

        Args:
            session_id: The session identifier.
            state: The state to save.
        """
        if session_id in self._sessions:
            self._sessions[session_id]["state"] = state
            self._sessions[session_id]["updated_at"] = datetime.utcnow().isoformat()

            logger.debug(
                "session_state_saved",
                session_id=session_id,
            )

    async def fail(self, session_id: str, reason: str = "") -> None:
        """Mark a session as failed.

        Args:
            session_id: The session identifier.
            reason: Optional reason for failure.
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
        """Mark a session as completed.

        Args:
            session_id: The session identifier.
        """
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = "completed"
            self._sessions[session_id]["completed_at"] = datetime.utcnow().isoformat()

            logger.info(
                "session_completed",
                session_id=session_id,
            )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session metadata.

        Args:
            session_id: The session identifier.

        Returns:
            Session metadata, or None if not found.
        """
        return self._sessions.get(session_id)

    def has_session(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: The session identifier.

        Returns:
            True if the session exists.
        """
        return session_id in self._sessions

    def clear_session(self, session_id: str) -> bool:
        """Clear a session from memory.

        Args:
            session_id: The session identifier.

        Returns:
            True if the session was cleared.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False


__all__ = ["SessionService"]