"""IncidentService 回归测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.incident import Incident, IncidentStatus
from app.repositories.incident_repository import InMemoryIncidentRepository
from app.services.incident_service import IncidentService


@pytest.mark.asyncio
async def test_list_incidents_sorts_mixed_naive_and_aware_created_at() -> None:
    """历史数据混有 naive/aware 时间时，列表接口也应稳定排序而不是直接抛异常。"""

    repository = InMemoryIncidentRepository()
    service = IncidentService(repository=repository)

    older = Incident(
        id="inc_older",
        title="older",
        status=IncidentStatus.CLOSED,
        created_at=datetime(2026, 3, 10, 10, 0, 0),
    )
    newer = Incident(
        id="inc_newer",
        title="newer",
        status=IncidentStatus.CLOSED,
        created_at=datetime(2026, 3, 11, 10, 0, 0, tzinfo=UTC),
    )

    await repository.create(older)
    await repository.create(newer)

    result = await service.list_incidents(status=IncidentStatus.CLOSED, page=1, page_size=10)

    assert [item.id for item in result.items] == ["inc_newer", "inc_older"]
