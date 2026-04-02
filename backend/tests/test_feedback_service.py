"""FeedbackService 的 SQLite 持久化测试。"""

from __future__ import annotations

from app.services.feedback_service import FeedbackService
from app.storage.sqlite_store import SqliteStore


async def test_feedback_service_persists_to_sqlite(tmp_path):
    """验证反馈记录会写入 SQLite 并按倒序返回。"""

    service = FeedbackService()
    service._store = SqliteStore(str(tmp_path / "feedback.db"))  # noqa: SLF001 - test inject isolated db

    first = await service.append({"score": 3, "comment": "first"})
    second = await service.append({"score": 5, "comment": "second"})
    rows = await service.list(limit=10)

    assert first["id"].startswith("fbk_")
    assert rows[0]["comment"] == "second"
    assert rows[1]["comment"] == "first"
