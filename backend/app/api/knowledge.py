"""知识库管理 API。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.knowledge import (
    CaseFields,
    KnowledgeEntry,
    KnowledgeEntryType,
    PostmortemTemplateFields,
    RunbookFields,
)
from app.services.knowledge_service import knowledge_service

router = APIRouter()


class KnowledgeEntryUpsertRequest(BaseModel):
    """知识条目创建/更新请求。"""

    entry_type: KnowledgeEntryType
    title: str
    summary: str = ""
    content: str = ""
    tags: List[str] = Field(default_factory=list)
    service_names: List[str] = Field(default_factory=list)
    domain: str = ""
    aggregate: str = ""
    author: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    case_fields: Optional[CaseFields] = None
    runbook_fields: Optional[RunbookFields] = None
    postmortem_fields: Optional[PostmortemTemplateFields] = None


class KnowledgeListResponse(BaseModel):
    items: List[KnowledgeEntry]
    total: int


@router.get("/entries", response_model=KnowledgeListResponse)
async def list_knowledge_entries(
    entry_type: Optional[KnowledgeEntryType] = Query(None),
    q: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
) -> KnowledgeListResponse:
    items = await knowledge_service.list_entries(entry_type=entry_type, q=q, tag=tag)
    return KnowledgeListResponse(items=items, total=len(items))


@router.get("/entries/{entry_id}", response_model=KnowledgeEntry)
async def get_knowledge_entry(entry_id: str) -> KnowledgeEntry:
    item = await knowledge_service.get_entry(entry_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")
    return item


@router.post("/entries", response_model=KnowledgeEntry, status_code=status.HTTP_201_CREATED)
async def create_knowledge_entry(request: KnowledgeEntryUpsertRequest) -> KnowledgeEntry:
    return await knowledge_service.create_entry(**request.model_dump())


@router.put("/entries/{entry_id}", response_model=KnowledgeEntry)
async def update_knowledge_entry(entry_id: str, request: KnowledgeEntryUpsertRequest) -> KnowledgeEntry:
    updated = await knowledge_service.update_entry(entry_id=entry_id, **request.model_dump())
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")
    return updated


@router.delete("/entries/{entry_id}")
async def delete_knowledge_entry(entry_id: str) -> Dict[str, Any]:
    deleted = await knowledge_service.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识条目不存在")
    return {"deleted": True, "entry_id": entry_id}


@router.get("/stats")
async def get_knowledge_stats() -> Dict[str, int]:
    return await knowledge_service.stats()
