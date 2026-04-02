"""ReportRepository 的 SQLite 行为测试。"""

from __future__ import annotations

from app.repositories.report_repository import SqliteReportRepository
from app.storage.sqlite_store import SqliteStore


async def test_sqlite_report_repository_supports_versions_and_share_tokens(tmp_path):
    """验证报告历史与 share token 映射会持久化到 SQLite。"""

    store = SqliteStore(str(tmp_path / "report.db"))
    repo = SqliteReportRepository(store)

    await repo.save(
        {
            "report_id": "rpt_1",
            "incident_id": "inc_1",
            "format": "markdown",
            "generated_at": "2026-03-25T10:00:00Z",
            "content": "v1",
        }
    )
    await repo.save(
        {
            "report_id": "rpt_2",
            "incident_id": "inc_1",
            "format": "markdown",
            "generated_at": "2026-03-25T10:05:00Z",
            "content": "v2",
        }
    )
    await repo.save(
        {
            "report_id": "rpt_json",
            "incident_id": "inc_1",
            "format": "json",
            "generated_at": "2026-03-25T10:06:00Z",
            "content": "{\"ok\":true}",
        }
    )

    latest = await repo.get_latest("inc_1")
    latest_md = await repo.get_latest_by_format("inc_1", "markdown")
    items = await repo.list_by_incident("inc_1")

    assert latest is not None
    assert latest["report_id"] == "rpt_json"
    assert latest_md is not None
    assert latest_md["report_id"] == "rpt_2"
    assert [item["report_id"] for item in items] == ["rpt_1", "rpt_2", "rpt_json"]

    await repo.save_share_token("token_1", "inc_1")
    assert await repo.get_incident_id_by_share_token("token_1") == "inc_1"
