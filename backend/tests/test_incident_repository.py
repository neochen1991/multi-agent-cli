"""IncidentRepository 的 SQLite 行为测试。"""

from __future__ import annotations

from app.models.incident import Incident, IncidentSeverity, IncidentSource, IncidentStatus
from app.repositories.incident_repository import SqliteIncidentRepository
from app.storage.sqlite_store import SqliteStore


async def test_sqlite_incident_repository_crud(tmp_path):
    """验证 incident 在 SQLite 仓储中的增删改查。"""

    store = SqliteStore(str(tmp_path / "incident.db"))
    repo = SqliteIncidentRepository(store)
    incident = Incident(
        id="inc_1",
        title="订单创建失败",
        description="POST /api/v1/orders 502",
        status=IncidentStatus.ANALYZING,
        severity=IncidentSeverity.HIGH,
        source=IncidentSource.MONITOR,
    )

    await repo.create(incident)
    loaded = await repo.get("inc_1")
    assert loaded is not None
    assert loaded.title == "订单创建失败"

    incident.root_cause = "downstream timeout"
    await repo.update(incident)
    updated = await repo.get("inc_1")
    assert updated is not None
    assert updated.root_cause == "downstream timeout"

    items = await repo.list_all()
    assert [item.id for item in items] == ["inc_1"]

    deleted = await repo.delete("inc_1")
    assert deleted is True
    assert await repo.get("inc_1") is None
