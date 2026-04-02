"""DebateRepository 的 SQLite 行为测试。"""

from __future__ import annotations

from app.models.debate import DebateResult, DebateSession, DebateStatus
from app.repositories.debate_repository import SqliteDebateRepository
from app.storage.sqlite_store import SqliteStore


async def test_sqlite_debate_repository_persists_sessions_and_results(tmp_path):
    """验证 debate 会话与结果会分别落到 SQLite 表中。"""

    store = SqliteStore(str(tmp_path / "debate.db"))
    repo = SqliteDebateRepository(store)

    session = DebateSession(
        id="deb_1",
        incident_id="inc_1",
        status=DebateStatus.RUNNING,
        current_round=1,
    )
    await repo.save_session(session)

    result = DebateResult(
        session_id="deb_1",
        incident_id="inc_1",
        root_cause="order-service timeout",
        confidence=0.71,
    )
    await repo.save_result(result)

    loaded_session = await repo.get_session("deb_1")
    loaded_result = await repo.get_result("deb_1")
    sessions = await repo.list_sessions()

    assert loaded_session is not None
    assert loaded_session.incident_id == "inc_1"
    assert loaded_result is not None
    assert loaded_result.root_cause == "order-service timeout"
    assert [item.id for item in sessions] == ["deb_1"]
