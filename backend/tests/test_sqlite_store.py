"""统一 SQLite 存储基础设施测试。"""

from __future__ import annotations

from app.storage.sqlite_store import SqliteStore


async def test_sqlite_store_initializes_schema_and_supports_roundtrip(tmp_path):
    """验证首次初始化会自动建表，并能完成 JSON 写读。"""

    db_path = tmp_path / "app.db"
    store = SqliteStore(str(db_path))

    await store.execute(
        "INSERT INTO feedback_items (id, created_at, payload_json) VALUES (?, ?, ?)",
        ("fb_1", "2026-03-25T00:00:00Z", store.dumps_json({"score": 5, "label": "ok"})),
    )

    row = await store.fetchone(
        "SELECT id, payload_json FROM feedback_items WHERE id = ?",
        ("fb_1",),
    )

    assert row is not None
    assert row["id"] == "fb_1"
    assert store.loads_json(row["payload_json"], {}) == {"score": 5, "label": "ok"}


async def test_sqlite_store_reuses_existing_database_without_losing_tables(tmp_path):
    """验证复用同一数据库文件时，不会破坏已存在表结构与数据。"""

    db_path = tmp_path / "shared.db"
    first = SqliteStore(str(db_path))
    await first.execute(
        "INSERT INTO remediation_actions (id, created_at, payload_json) VALUES (?, ?, ?)",
        ("act_1", "2026-03-25T01:00:00Z", first.dumps_json({"status": "pending"})),
    )

    second = SqliteStore(str(db_path))
    row = await second.fetchone(
        "SELECT payload_json FROM remediation_actions WHERE id = ?",
        ("act_1",),
    )

    assert row is not None
    assert second.loads_json(row["payload_json"], {})["status"] == "pending"
