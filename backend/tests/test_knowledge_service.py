"""知识库服务测试。"""

import pytest

from app.config import settings
from app.models.knowledge import CaseFields, KnowledgeEntryType
from app.repositories.knowledge_repository import FileKnowledgeRepository
from app.services.knowledge_service import KnowledgeService


async def _build_service(tmp_path, monkeypatch) -> KnowledgeService:
    monkeypatch.setattr(settings, "LOCAL_STORE_BACKEND", "file")
    monkeypatch.setattr(settings, "LOCAL_STORE_DIR", str(tmp_path))
    repo = FileKnowledgeRepository()
    monkeypatch.setattr("app.services.knowledge_service.knowledge_repository", repo)
    service = KnowledgeService()
    return service


@pytest.mark.asyncio
async def test_knowledge_service_crud_and_persist(tmp_path, monkeypatch):
    """验证知识条目可创建、更新、删除，并写入 markdown。"""

    service = await _build_service(tmp_path, monkeypatch)

    created = await service.create_entry(
        entry_type=KnowledgeEntryType.CASE,
        title="支付接口 504",
        summary="网关超时案例",
        content="这是一个用于测试的案例正文。",
        tags=["payment", "504"],
        service_names=["payment-service"],
        domain="payment",
        aggregate="PaymentAggregate",
        author="tester",
        case_fields=CaseFields(
            incident_type="gateway_timeout",
            symptoms=["/api/v1/payments 504"],
            root_cause="下游超时",
            solution="扩容并限流",
            fix_steps=["检查网关", "检查下游"],
        ),
    )

    assert created.id.startswith("kb_")
    stored_file = tmp_path / "knowledge" / "cases" / f"{created.id}.md"
    assert stored_file.exists()

    loaded = await service.get_entry(created.id)
    assert loaded is not None
    assert loaded.title == "支付接口 504"
    assert loaded.case_fields is not None
    assert loaded.case_fields.root_cause == "下游超时"

    updated = await service.update_entry(
        entry_id=created.id,
        entry_type=KnowledgeEntryType.CASE,
        title="支付接口 504 已更新",
        summary="更新后的摘要",
        content="更新后的正文",
        tags=["payment", "timeout"],
        service_names=["payment-service"],
        domain="payment",
        aggregate="PaymentAggregate",
        author="tester",
        case_fields=CaseFields(
            incident_type="gateway_timeout",
            symptoms=["/api/v1/payments 504"],
            root_cause="连接池阻塞",
            solution="优化超时配置",
            fix_steps=["步骤1"],
        ),
    )
    assert updated is not None
    assert updated.title == "支付接口 504 已更新"

    deleted = await service.delete_entry(created.id)
    assert deleted is True
    assert await service.get_entry(created.id) is None


@pytest.mark.asyncio
async def test_knowledge_service_filters_and_stats(tmp_path, monkeypatch):
    """验证知识条目过滤和统计。"""

    service = await _build_service(tmp_path, monkeypatch)
    service._bootstrapped = True  # noqa: SLF001 - test setup

    await service.create_entry(
        entry_type=KnowledgeEntryType.RUNBOOK,
        title="订单 5xx 排查",
        summary="订单 Runbook",
        content="订单系统 runbook",
        tags=["orders", "runbook"],
        service_names=["order-service"],
        domain="order",
        aggregate="OrderAggregate",
        author="tester",
    )
    await service.create_entry(
        entry_type=KnowledgeEntryType.POSTMORTEM_TEMPLATE,
        title="数据库故障复盘模板",
        summary="模板摘要",
        content="模板正文",
        tags=["db", "template"],
        service_names=["mysql"],
        domain="infra",
        aggregate="DatabaseAggregate",
        author="tester",
    )

    runbooks = await service.list_entries(entry_type=KnowledgeEntryType.RUNBOOK)
    assert len(runbooks) == 1
    assert runbooks[0].entry_type == KnowledgeEntryType.RUNBOOK

    searched = await service.list_entries(q="数据库")
    assert len(searched) == 1
    assert searched[0].title == "数据库故障复盘模板"

    stats = await service.stats()
    assert stats["total"] == 2
    assert stats["runbook"] == 1
    assert stats["postmortem_template"] == 1
