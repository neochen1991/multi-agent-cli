"""testAgent工具上下文服务相关测试。"""

from __future__ import annotations

import sqlite3
import subprocess

import pytest

from app.models.tooling import AgentToolingConfig, DatabaseToolConfig
from app.services.agent_tool_context_service import AgentToolContextService


def test_collect_recent_git_changes_handles_repo_without_commits(tmp_path):
    """验证collect最近Git变更处理repo无commits。"""
    
    subprocess.run(
        ["git", "init"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )

    service = AgentToolContextService()
    audit_log = []
    changes = service._collect_recent_git_changes(  # noqa: SLF001 - testing internal fallback behavior
        str(tmp_path),
        20,
        audit_log,
    )

    assert changes == []
    assert any(
        str(item.get("action") or "") == "git_log_changes" and str(item.get("status") or "") == "unavailable"
        for item in audit_log
    )


def test_extract_keywords_uses_investigation_leads():
    """验证提取关键词使用investigation线索。"""
    
    service = AgentToolContextService()

    keywords = service._extract_keywords(  # noqa: SLF001 - validating lead expansion logic
        {
            "log_excerpt": "timeout on orders",
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "class_names": ["OrderController", "OrderService"],
                "code_artifacts": ["order/service/OrderService.java"],
                "database_tables": ["t_order"],
                "monitor_items": ["order.error.rate"],
                "dependency_services": ["inventory-service"],
                "trace_ids": ["trace-001"],
                "error_keywords": ["timeout"],
            },
        },
        {},
        {"task": "根据已知线索定位问题"},
    )

    assert "orders" in keywords
    assert "order-service" in keywords
    assert "ordercontroller" in keywords
    assert "t_order" in keywords
    assert "inventory-service" in keywords


def test_collect_metrics_signals_preserves_db_connection_ratio():
    """验证指标提取会保留数据库连接比值。"""

    service = AgentToolContextService()

    signals = service._collect_metrics_signals(  # noqa: SLF001 - validating metric parsing logic
        {"log_excerpt": "order.error.rate=18.7% hikari_pending=87 db_conn=20/20"},
        {},
    )

    db_signal = next(item for item in signals if item.get("metric") == "db_conn")
    assert db_signal["value"] == "20/20"


@pytest.mark.asyncio
async def test_database_agent_context_reads_sqlite_snapshot(tmp_path, monkeypatch):
    """验证databaseAgent上下文读取SQLite快照。"""
    
    db_path = tmp_path / "ops_snapshot.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE t_order (id INTEGER PRIMARY KEY, sku_id TEXT, status TEXT)")
        cur.execute("CREATE INDEX idx_order_sku ON t_order(sku_id)")
        cur.execute("CREATE TABLE slow_sql (sql_text TEXT, duration_ms INTEGER)")
        cur.execute("INSERT INTO slow_sql(sql_text, duration_ms) VALUES (?, ?)", ("SELECT * FROM t_order", 30123))
        cur.execute("CREATE TABLE top_sql (sql_text TEXT, exec_count INTEGER)")
        cur.execute("INSERT INTO top_sql(sql_text, exec_count) VALUES (?, ?)", ("SELECT id FROM t_order", 889))
        cur.execute("CREATE TABLE session_status (active_sessions INTEGER, running INTEGER)")
        cur.execute("INSERT INTO session_status(active_sessions, running) VALUES (?, ?)", (112, 45))
        conn.commit()
    finally:
        conn.close()

    async def _fake_get_config():
        """为测试场景提供get配置模拟实现。"""
        return AgentToolingConfig(
            database=DatabaseToolConfig(enabled=True, db_path=str(db_path), max_rows=10),
        )

    monkeypatch.setattr("app.services.agent_tool_context_service.tooling_service.get_config", _fake_get_config)

    service = AgentToolContextService()
    payload = await service.build_context(
        agent_name="DatabaseAgent",
        compact_context={"log_excerpt": "orders timeout"},
        incident_context={"description": "/orders 502 with db lock"},
        assigned_command={
            "task": "读取数据库慢sql和索引",
            "focus": "slow sql + index",
            "database_tables": ["t_order"],
            "use_tool": True,
        },
    )

    assert payload["name"] == "db_snapshot_reader"
    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert int(payload["data"]["table_count"]) == 1
    assert payload["data"]["tables"] == ["t_order"]
    assert payload["data"]["requested_tables"] == ["t_order"]
    assert len(payload["data"]["slow_sql"]) == 1
    assert len(payload["data"]["top_sql"]) == 1
    assert len(payload["data"]["session_status"]) == 1
    assert any(
        str(item.get("action") or "") == "sqlite_query" and str(item.get("status") or "") == "ok"
        for item in list(payload.get("audit_log") or [])
    )


@pytest.mark.asyncio
async def test_database_agent_context_reads_postgres_snapshot(monkeypatch):
    """验证databaseAgent上下文读取Postgres快照。"""
    
    class _FakeConn:
        """为测试场景提供FakeConn辅助对象。"""
        async def fetch(self, sql, *args):  # noqa: ANN001, ANN002
            """为测试场景提供fetch辅助逻辑。"""
            text = str(sql)
            if "information_schema.tables" in text:
                return [{"table_name": "t_order"}, {"table_name": "t_order_item"}]
            if "information_schema.columns" in text:
                table = str(args[1] if len(args) > 1 else "")
                if table == "t_order":
                    return [
                        {"column_name": "id", "data_type": "bigint", "is_nullable": "NO", "column_default": None, "ordinal_position": 1},
                        {"column_name": "status", "data_type": "varchar", "is_nullable": "YES", "column_default": None, "ordinal_position": 2},
                    ]
                return [
                    {"column_name": "order_id", "data_type": "bigint", "is_nullable": "NO", "column_default": None, "ordinal_position": 1},
                    {"column_name": "sku_id", "data_type": "varchar", "is_nullable": "YES", "column_default": None, "ordinal_position": 2},
                ]
            if "FROM pg_indexes" in text:
                return [{"indexname": "idx_order_status", "indexdef": "CREATE INDEX idx_order_status ON t_order(status)"}]
            if "pg_stat_statements" in text and "total_exec_time" in text:
                return [{"query": "select * from t_order", "calls": 101, "total_exec_time": 2200.0, "mean_exec_time": 21.8, "rows": 99}]
            if "pg_stat_statements" in text and "ORDER BY calls" in text:
                return [{"query": "select id from t_order", "calls": 880, "total_exec_time": 850.0, "mean_exec_time": 1.0, "rows": 880}]
            if "FROM pg_stat_activity" in text:
                return [{"state": "active", "wait_event_type": "Lock", "wait_event": "transactionid", "sessions": 14}]
            return []

        async def close(self):
            """为测试场景提供关闭辅助逻辑。"""
            return None

    class _FakeAsyncpg:
        """为测试场景提供FakeAsyncpg辅助对象。"""

        @staticmethod
        async def connect(**kwargs):  # noqa: ANN003
            """为测试场景提供connect辅助逻辑。"""
            assert "dsn" in kwargs
            return _FakeConn()

    async def _fake_get_config():
        """为测试场景提供get配置模拟实现。"""
        return AgentToolingConfig(
            database=DatabaseToolConfig(
                enabled=True,
                engine="postgresql",
                postgres_dsn="postgresql://user:pwd@localhost:5432/order_db",
                pg_schema="public",
                max_rows=10,
                connect_timeout_seconds=5,
            ),
        )

    monkeypatch.setattr("app.services.agent_tool_context_service.asyncpg", _FakeAsyncpg())
    monkeypatch.setattr("app.services.agent_tool_context_service.tooling_service.get_config", _fake_get_config)

    service = AgentToolContextService()
    payload = await service.build_context(
        agent_name="DatabaseAgent",
        compact_context={"log_excerpt": "orders timeout"},
        incident_context={"description": "/orders 502 with db lock"},
        assigned_command={
            "task": "分析postgres慢sql和session",
            "focus": "slow sql + session",
            "database_tables": ["public.t_order"],
            "use_tool": True,
        },
    )

    assert payload["name"] == "db_snapshot_reader"
    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert payload["data"]["engine"] == "postgresql"
    assert int(payload["data"]["table_count"]) == 1
    assert payload["data"]["tables"] == ["t_order"]
    assert payload["data"]["requested_tables"] == ["public.t_order"]
    assert len(payload["data"]["slow_sql"]) == 1
    assert len(payload["data"]["top_sql"]) == 1
    assert len(payload["data"]["session_status"]) == 1
    assert any(
        str(item.get("action") or "") == "postgres_query" and str(item.get("status") or "") == "ok"
        for item in list(payload.get("audit_log") or [])
    )
