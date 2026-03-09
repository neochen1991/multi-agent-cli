"""知识库服务。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.knowledge import (
    CaseFields,
    KnowledgeEntry,
    KnowledgeEntryType,
    PostmortemTemplateFields,
    RunbookFields,
)
from app.repositories.knowledge_repository import knowledge_repository


class KnowledgeService:
    """统一管理知识条目。"""

    def __init__(self) -> None:
        self._bootstrapped = False

    async def list_entries(
        self,
        entry_type: Optional[KnowledgeEntryType] = None,
        q: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[KnowledgeEntry]:
        await self._ensure_bootstrap()
        rows = await knowledge_repository.list()
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        if entry_type:
            rows = [item for item in rows if item.entry_type == entry_type]
        if tag:
            rows = [item for item in rows if tag in item.tags]
        if q:
            query = q.strip().lower()
            rows = [
                item for item in rows
                if query in " ".join(
                    [
                        item.title,
                        item.summary,
                        item.content,
                        item.domain,
                        item.aggregate,
                        " ".join(item.tags),
                        " ".join(item.service_names),
                    ]
                ).lower()
            ]
        return rows

    async def get_entry(self, entry_id: str) -> Optional[KnowledgeEntry]:
        await self._ensure_bootstrap()
        return await knowledge_repository.get(entry_id)

    async def create_entry(
        self,
        entry_type: KnowledgeEntryType,
        title: str,
        summary: str,
        content: str,
        tags: Optional[List[str]] = None,
        service_names: Optional[List[str]] = None,
        domain: str = "",
        aggregate: str = "",
        author: str = "",
        metadata: Optional[Dict[str, object]] = None,
        case_fields: Optional[CaseFields] = None,
        runbook_fields: Optional[RunbookFields] = None,
        postmortem_fields: Optional[PostmortemTemplateFields] = None,
    ) -> KnowledgeEntry:
        now = datetime.now(timezone.utc)
        entry = KnowledgeEntry(
            id=f"kb_{uuid.uuid4().hex[:10]}",
            entry_type=entry_type,
            title=title.strip(),
            summary=summary.strip(),
            content=content.strip(),
            tags=self._clean_list(tags),
            service_names=self._clean_list(service_names),
            domain=domain.strip(),
            aggregate=aggregate.strip(),
            author=author.strip(),
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
            case_fields=case_fields,
            runbook_fields=runbook_fields,
            postmortem_fields=postmortem_fields,
        )
        return await knowledge_repository.save(entry)

    async def update_entry(
        self,
        entry_id: str,
        entry_type: KnowledgeEntryType,
        title: str,
        summary: str,
        content: str,
        tags: Optional[List[str]] = None,
        service_names: Optional[List[str]] = None,
        domain: str = "",
        aggregate: str = "",
        author: str = "",
        metadata: Optional[Dict[str, object]] = None,
        case_fields: Optional[CaseFields] = None,
        runbook_fields: Optional[RunbookFields] = None,
        postmortem_fields: Optional[PostmortemTemplateFields] = None,
    ) -> Optional[KnowledgeEntry]:
        current = await self.get_entry(entry_id)
        if not current:
            return None
        updated = current.model_copy(
            update={
                "entry_type": entry_type,
                "title": title.strip(),
                "summary": summary.strip(),
                "content": content.strip(),
                "tags": self._clean_list(tags),
                "service_names": self._clean_list(service_names),
                "domain": domain.strip(),
                "aggregate": aggregate.strip(),
                "author": author.strip(),
                "metadata": metadata or {},
                "case_fields": case_fields,
                "runbook_fields": runbook_fields,
                "postmortem_fields": postmortem_fields,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return await knowledge_repository.save(updated)

    async def delete_entry(self, entry_id: str) -> bool:
        return await knowledge_repository.delete(entry_id)

    async def stats(self) -> Dict[str, int]:
        await self._ensure_bootstrap()
        return await knowledge_repository.stats()

    async def search_reference_entries(
        self,
        *,
        query: str,
        limit: int = 5,
        entry_types: Optional[List[KnowledgeEntryType]] = None,
    ) -> List[Dict[str, object]]:
        """为 Agent 检索可引用的知识条目。"""
        await self._ensure_bootstrap()
        allowed = set(entry_types or [KnowledgeEntryType.CASE, KnowledgeEntryType.RUNBOOK])
        rows = await self.list_entries(q=query or None)
        results: List[Dict[str, object]] = []
        for item in rows:
            if item.entry_type not in allowed:
                continue
            results.append(
                {
                    "id": item.id,
                    "entry_type": item.entry_type.value,
                    "title": item.title,
                    "summary": item.summary,
                    "content": item.content,
                    "tags": list(item.tags or []),
                    "service_names": list(item.service_names or []),
                    "domain": item.domain,
                    "aggregate": item.aggregate,
                    "updated_at": item.updated_at.isoformat(),
                    "case_fields": item.case_fields.model_dump(mode="json") if item.case_fields else None,
                    "runbook_fields": item.runbook_fields.model_dump(mode="json") if item.runbook_fields else None,
                    "postmortem_fields": item.postmortem_fields.model_dump(mode="json") if item.postmortem_fields else None,
                }
            )
            if len(results) >= max(1, int(limit or 5)):
                break
        return results

    async def _ensure_bootstrap(self) -> None:
        if self._bootstrapped:
            return
        existing = await knowledge_repository.list()
        if existing:
            self._bootstrapped = True
            return
        await self.create_entry(
            entry_type=KnowledgeEntryType.CASE,
            title="订单接口 502：连接池耗尽导致下单失败",
            summary="典型表现为 orders 502、Hikari pending threads 飙高、数据库连接打满。",
            content="现象：下单接口 502，CPU 升高，数据库活跃连接达到上限。\n\n结论：长事务叠加库存更新锁等待，导致连接池耗尽。\n\n建议：先扩容连接池保护流量，再排查慢 SQL 和锁等待链。",
            tags=["orders", "db", "连接池", "502"],
            service_names=["order-service", "gateway"],
            domain="order",
            aggregate="OrderAggregate",
            author="system",
            case_fields=CaseFields(
                incident_type="database_contention",
                symptoms=["/api/v1/orders 502", "Hikari pending threads > 400", "db active 100/100"],
                root_cause="订单事务持有连接过久，叠加库存更新锁等待，导致连接池耗尽。",
                solution="限流、降级、排查慢 SQL、优化索引、缩短事务。",
                fix_steps=["限制入口流量", "导出慢 SQL", "分析锁等待链", "拆分长事务"],
            ),
        )
        await self.create_entry(
            entry_type=KnowledgeEntryType.RUNBOOK,
            title="网关 5xx 激增排查 SOP",
            summary="适用于网关 5xx/502/504 短时间快速升高的场景。",
            content="目标：10 分钟内判定故障位于网关、下游服务还是数据库。\n\n步骤包括：确认告警范围、检查网关错误分布、核对上游响应耗时、比对后端资源与依赖状态。",
            tags=["gateway", "5xx", "sop"],
            service_names=["gateway"],
            domain="platform",
            aggregate="GatewayAggregate",
            author="system",
            runbook_fields=RunbookFields(
                applicable_scenarios=["502 激增", "504 激增", "上游 timeout"],
                prechecks=["确认影响接口范围", "确认发布时间点", "查看网关错误码分布"],
                steps=["检查网关 access/error log", "对比下游服务耗时", "核对 DB/缓存连接状态"],
                rollback_plan=["若确认变更引起，回滚最近发布", "恢复网关限流策略到保守值"],
                verification_steps=["5xx 比例回落", "接口 P95 恢复", "错误日志停止增长"],
            ),
        )
        await self.create_entry(
            entry_type=KnowledgeEntryType.POSTMORTEM_TEMPLATE,
            title="生产故障复盘模板 v1",
            summary="用于团队复盘：时间线、影响面、5 Whys、改进项。",
            content="请在复盘会议后补齐每一项，并为每个行动项指定 owner 和截止时间。",
            tags=["postmortem", "template"],
            author="system",
            postmortem_fields=PostmortemTemplateFields(
                impact_scope_template=["受影响用户数", "受影响接口/服务", "业务损失评估"],
                timeline_template=["发现时间", "升级时间", "缓解时间", "恢复时间"],
                five_whys_template=["为什么会发生？", "为什么未提前发现？", "为什么保护措施未生效？"],
                action_items_template=["监控补齐", "限流/熔断策略完善", "设计/代码整改"],
            ),
        )
        self._bootstrapped = True

    @staticmethod
    def _clean_list(items: Optional[List[str]]) -> List[str]:
        return [str(item).strip() for item in (items or []) if str(item).strip()]


knowledge_service = KnowledgeService()
