"""WorkLogManager 的 SQLite 读取测试。"""

from __future__ import annotations

from app.runtime.langgraph.work_log_manager import WorkLogManager
from app.runtime.session_store import RuntimeSessionStore


async def test_work_log_manager_builds_context_from_sqlite_events(tmp_path):
    """验证 work log 会从 SQLite 事件表读取而不是 jsonl 文件。"""

    store = RuntimeSessionStore(str(tmp_path / "worklog.db"))
    await store.append_event(
        "deb_2",
        {
            "timestamp": "2026-03-25T10:01:00Z",
            "type": "agent_command_issued",
            "agent_name": "ProblemAnalysisAgent",
            "command": {"task": "分析订单超时", "focus": "impact"},
        },
    )
    await store.append_event(
        "deb_2",
        {
            "timestamp": "2026-03-25T10:01:01Z",
            "type": "agent_chat_message",
            "agent_name": "ImpactAnalysisAgent",
            "conclusion": "影响订单创建功能",
            "confidence": 0.6,
            "output_json": {"conclusion": "影响订单创建功能", "confidence": 0.6},
        },
    )

    manager = WorkLogManager()
    manager._store = store._store  # noqa: SLF001 - test inject dedicated sqlite db
    payload = manager.build_context("deb_2")

    assert payload["summary"]["commands"] == 1
    assert payload["summary"]["results"] == 1
    assert any(item["type"] == "command" for item in payload["items"])
    assert any(item["type"] == "result" for item in payload["items"])
