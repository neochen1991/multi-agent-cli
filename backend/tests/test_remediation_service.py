"""RemediationService 的 SQLite 持久化测试。"""

from __future__ import annotations

from app.services.remediation_service import RemediationService
from app.storage.sqlite_store import SqliteStore


async def test_remediation_service_persists_lifecycle_to_sqlite(tmp_path):
    """验证修复动作生命周期状态会持久化到 SQLite。"""

    service = RemediationService()
    service._store = SqliteStore(str(tmp_path / "remediation.db"))  # noqa: SLF001 - test inject isolated db

    proposed = await service.propose(
        incident_id="inc_1",
        session_id="deb_1",
        summary="扩容连接池",
        steps=["调整 hikari"],
        risk_level="medium",
        pre_slo={"error_rate": 0.2, "p95_latency_ms": 500},
    )
    simulated = await service.simulate(proposed["id"], {"error_rate": 0.1, "p95_latency_ms": 420})
    approved = await service.approve(proposed["id"], "alice")
    executed = await service.execute(
        proposed["id"],
        operator="bob",
        post_slo={"error_rate": 0.19, "p95_latency_ms": 530},
    )
    verified = await service.verify(proposed["id"], "carol", {"status": "ok"})

    assert simulated["state"] == "SIMULATED"
    assert approved["state"] == "APPROVED"
    assert executed["state"] == "EXECUTED"
    assert verified["state"] == "VERIFIED"
    assert (await service.get_action(proposed["id"]))["state"] == "VERIFIED"
