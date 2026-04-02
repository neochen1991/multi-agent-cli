"""LineageRecorder 的 SQLite 持久化测试。"""

from __future__ import annotations

from app.runtime.trace_lineage.recorder import LineageRecorder


async def test_lineage_recorder_reads_from_sqlite(tmp_path):
    """验证 lineage 记录会写入 SQLite 并可按顺序回放。"""

    recorder = LineageRecorder(str(tmp_path / "lineage.db"))
    await recorder.append(
        session_id="deb_3",
        kind="event",
        trace_id="tr_3",
        phase="analysis",
        agent_name="LogAgent",
        event_type="llm_call_started",
    )
    await recorder.append(
        session_id="deb_3",
        kind="agent",
        trace_id="tr_3",
        phase="analysis",
        agent_name="ImpactAnalysisAgent",
        event_type="agent_round",
        confidence=0.66,
        output_summary={"conclusion": "影响订单创建"},
    )

    rows = await recorder.read("deb_3")
    summary = await recorder.summarize("deb_3")

    assert [row.seq for row in rows] == [1, 2]
    assert rows[1].agent_name == "ImpactAnalysisAgent"
    assert summary["records"] == 2
    assert "ImpactAnalysisAgent" in summary["agents"]
