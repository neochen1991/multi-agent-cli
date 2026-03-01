"""Event dispatching utilities for LangGraph runtime."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.event_schema import enrich_event
from app.runtime.session_store import runtime_session_store


class EventDispatcher:
    """Persist + forward runtime events."""

    def __init__(
        self,
        *,
        trace_id: str = "",
        session_id: str = "",
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self._trace_id = str(trace_id or "")
        self._session_id = str(session_id or "")
        self._callback = callback
        self._event_sequence = 0

    def bind(
        self,
        *,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        if trace_id is not None:
            self._trace_id = str(trace_id or "")
        if session_id is not None:
            next_session = str(session_id or "")
            if next_session != self._session_id:
                self._event_sequence = 0
            self._session_id = next_session
        if callback is not None:
            self._callback = callback

    async def emit(self, event: Dict[str, Any]) -> None:
        self._event_sequence += 1
        outbound = dict(event or {})
        outbound.setdefault("event_sequence", self._event_sequence)
        if self._session_id and "session_id" not in outbound:
            outbound["session_id"] = self._session_id
        payload = enrich_event(
            outbound,
            trace_id=self._trace_id or None,
            default_phase=str(outbound.get("phase") or ""),
        )
        await runtime_session_store.append_event(
            self._session_id or "unknown",
            payload,
        )
        if not self._callback:
            return
        maybe = self._callback(payload)
        if asyncio.iscoroutine(maybe):
            await maybe


__all__ = ["EventDispatcher"]
