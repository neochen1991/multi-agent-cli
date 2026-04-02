"""RuntimeSessionStore 的 SQLite 持久化测试。"""

from __future__ import annotations

from app.runtime.messages import FinalVerdict, RoundCheckpoint
from app.runtime.session_store import RuntimeSessionStore


async def test_runtime_session_store_persists_state_and_events(tmp_path):
    """验证运行时状态与事件会写入 SQLite 并可回读。"""

    store = RuntimeSessionStore(str(tmp_path / "runtime.db"))
    state = await store.create(
        session_id="deb_1",
        trace_id="tr_1",
        context_summary={"title": "order timeout"},
    )
    assert state.session_id == "deb_1"

    await store.append_round(
        "deb_1",
        RoundCheckpoint(
            session_id="deb_1",
            round_number=1,
            loop_round=1,
            phase="analysis",
            agent_name="LogAgent",
            confidence=0.55,
            summary="first round",
            conclusion="log timeout",
        ),
    )
    await store.append_event(
        "deb_1",
        {"timestamp": "2026-03-25T10:00:00Z", "type": "agent_command_issued", "agent_name": "ProblemAnalysisAgent"},
    )
    await store.complete(
        "deb_1",
        FinalVerdict(root_cause={"summary": "downstream timeout", "confidence": 0.7}),
    )

    loaded = await store.load("deb_1")
    events = await store.list_events("deb_1")

    assert loaded is not None
    assert loaded.status == "completed"
    assert loaded.final_verdict is not None
    assert loaded.final_verdict.root_cause["summary"] == "downstream timeout"
    assert len(loaded.rounds) == 1
    assert events[0]["type"] == "agent_command_issued"
