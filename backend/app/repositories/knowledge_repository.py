"""知识库 markdown 仓储。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.models.knowledge import KnowledgeEntry, KnowledgeEntryType


class KnowledgeRepository:
    """知识条目仓储接口。"""

    async def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        raise NotImplementedError

    async def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        raise NotImplementedError

    async def list(self) -> List[KnowledgeEntry]:
        raise NotImplementedError

    async def delete(self, entry_id: str) -> bool:
        raise NotImplementedError

    async def stats(self) -> Dict[str, int]:
        raise NotImplementedError


class FileKnowledgeRepository(KnowledgeRepository):
    """使用本地 markdown 或内存保存知识条目。"""

    def __init__(self) -> None:
        self._entries: Dict[str, KnowledgeEntry] = {}
        root = Path(settings.LOCAL_STORE_DIR) / "knowledge"
        self._type_dirs = {
            KnowledgeEntryType.CASE: root / "cases",
            KnowledgeEntryType.RUNBOOK: root / "runbooks",
            KnowledgeEntryType.POSTMORTEM_TEMPLATE: root / "postmortems",
        }
        if settings.LOCAL_STORE_BACKEND == "file":
            for path in self._type_dirs.values():
                path.mkdir(parents=True, exist_ok=True)

    async def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        self._entries[entry.id] = entry
        if settings.LOCAL_STORE_BACKEND == "file":
            self._persist(entry)
        return entry

    async def get(self, entry_id: str) -> Optional[KnowledgeEntry]:
        cached = self._entries.get(entry_id)
        if cached:
            return cached
        if settings.LOCAL_STORE_BACKEND != "file":
            return None
        for path in self._type_dirs.values():
            file = path / f"{entry_id}.md"
            if not file.exists():
                continue
            loaded = self._load(file)
            if loaded:
                self._entries[loaded.id] = loaded
                return loaded
        return None

    async def list(self) -> List[KnowledgeEntry]:
        if settings.LOCAL_STORE_BACKEND == "file":
            for path in self._type_dirs.values():
                for file in path.glob("*.md"):
                    entry_id = file.stem
                    if entry_id in self._entries:
                        continue
                    loaded = self._load(file)
                    if loaded:
                        self._entries[loaded.id] = loaded
        return list(self._entries.values())

    async def delete(self, entry_id: str) -> bool:
        entry = await self.get(entry_id)
        if not entry:
            return False
        self._entries.pop(entry_id, None)
        if settings.LOCAL_STORE_BACKEND == "file":
            file = self._type_dirs[entry.entry_type] / f"{entry_id}.md"
            if file.exists():
                file.unlink()
        return True

    async def stats(self) -> Dict[str, int]:
        items = await self.list()
        return {
            "total": len(items),
            "case": sum(1 for item in items if item.entry_type == KnowledgeEntryType.CASE),
            "runbook": sum(1 for item in items if item.entry_type == KnowledgeEntryType.RUNBOOK),
            "postmortem_template": sum(
                1 for item in items if item.entry_type == KnowledgeEntryType.POSTMORTEM_TEMPLATE
            ),
        }

    def _persist(self, entry: KnowledgeEntry) -> None:
        payload = entry.model_dump(mode="json")
        content = str(payload.pop("content", "") or "")
        file = self._type_dirs[entry.entry_type] / f"{entry.id}.md"
        file.write_text(
            "---\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "---\n\n"
            f"{content.strip()}\n",
            encoding="utf-8",
        )

    def _load(self, file: Path) -> Optional[KnowledgeEntry]:
        try:
            raw = file.read_text(encoding="utf-8")
            if not raw.startswith("---\n"):
                return None
            parts = raw.split("\n---\n", 1)
            if len(parts) < 2:
                return None
            meta = parts[0].replace("---\n", "", 1).strip()
            body = parts[1].lstrip("\n")
            payload = json.loads(meta)
            payload["content"] = body.rstrip()
            return KnowledgeEntry(**payload)
        except Exception:
            return None


knowledge_repository = FileKnowledgeRepository()
