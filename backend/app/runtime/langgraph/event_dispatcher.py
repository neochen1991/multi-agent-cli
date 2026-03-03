"""Event dispatching utilities for LangGraph runtime."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.event_schema import enrich_event
from app.runtime.session_store import runtime_session_store
from app.runtime.trace_lineage import lineage_recorder


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
        await self._append_lineage(payload)
        if not self._callback:
            return
        maybe = self._callback(payload)
        if asyncio.iscoroutine(maybe):
            await maybe

    async def _append_lineage(self, payload: Dict[str, Any]) -> None:
        session_id = str(payload.get("session_id") or self._session_id or "unknown")
        event_type = str(payload.get("type") or "")
        phase = str(payload.get("phase") or "")
        agent_name = str(payload.get("agent_name") or "")
        output_summary = {}
        if isinstance(payload.get("output_json"), dict):
            output = payload.get("output_json") or {}
            output_summary = {
                "conclusion": str(output.get("conclusion") or "")[:260],
                "confidence": float(output.get("confidence") or 0.0),
            }
        input_summary = {}
        if "prompt_length" in payload or "prompt_preview" in payload:
            input_summary = {
                "prompt_length": int(payload.get("prompt_length") or 0),
                "prompt_preview": str(payload.get("prompt_preview") or "")[:320],
            }
        kind = "event"
        if event_type in {"agent_round", "agent_chat_message"}:
            kind = "agent"
        elif event_type.startswith("tool_") or "tool" in event_type:
            kind = "tool"
        await lineage_recorder.append(
            session_id=session_id,
            trace_id=str(payload.get("trace_id") or self._trace_id or ""),
            kind=kind,
            phase=phase,
            agent_name=agent_name,
            event_type=event_type,
            confidence=float(payload.get("confidence") or 0.0),
            duration_ms=float(payload.get("latency_ms") or 0.0),
            input_summary=input_summary,
            output_summary=output_summary,
            payload={
                "event_id": payload.get("event_id"),
                "event_sequence": payload.get("event_sequence"),
                "message": str(payload.get("message") or "")[:240],
            },
        )


__all__ = ["EventDispatcher"]
