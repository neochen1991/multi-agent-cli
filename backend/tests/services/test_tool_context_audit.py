"""Tool audit builder tests."""

from app.services.tool_context.audit import ToolAuditBuilder


def test_tool_audit_builder_generates_stable_call_ids_and_summaries():
    builder = ToolAuditBuilder()

    preview = builder.command_preview(
        {
            "task": "分析数据库锁等待",
            "focus": "top sql 与 session wait",
            "expected_output": "给出 blocker chain",
            "use_tool": True,
            "skill_hints": ["postgres", "explain"],
        }
    )
    entry = builder.build_entry(
        tool_name="db_snapshot_reader",
        action="remote_fetch",
        status="ok",
        detail={
            "service_name": "order-service",
            "query": "SELECT * FROM pg_stat_activity",
            "status": "ok",
            "result_count": 3,
            "elapsed_ms": 32.5,
        },
    )

    assert preview["task"] == "分析数据库锁等待"
    assert preview["skill_hints"] == ["postgres", "explain"]
    assert entry["call_id"].startswith("db_snapshot_reader_remote_fetch_")
    assert entry["request_summary"] == "query=SELECT * FROM pg_stat_activity；service_name=order-service"
    assert entry["response_summary"] == "status=ok；result_count=3"
    assert entry["duration_ms"] == 32.5
