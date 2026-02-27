"""Tests for EventDispatcher."""

import pytest

from app.runtime.langgraph.event_dispatcher import EventDispatcher


@pytest.mark.asyncio
async def test_event_dispatcher_injects_session_and_trace():
    captured = {}

    async def _cb(payload):
        captured.update(payload)

    dispatcher = EventDispatcher(trace_id="tr_test", session_id="ses_test", callback=_cb)
    await dispatcher.emit({"type": "hello", "phase": "analysis"})

    assert captured.get("type") == "hello"
    assert captured.get("session_id") == "ses_test"
    assert captured.get("trace_id") == "tr_test"
