"""
故障事件仓储
Incident Repository
"""

from abc import ABC, abstractmethod
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.models.incident import Incident


class IncidentRepository(ABC):
    """故障事件仓储接口"""

    @abstractmethod
    async def create(self, incident: Incident) -> Incident:
        pass

    @abstractmethod
    async def get(self, incident_id: str) -> Optional[Incident]:
        pass

    @abstractmethod
    async def update(self, incident: Incident) -> Incident:
        pass

    @abstractmethod
    async def delete(self, incident_id: str) -> bool:
        pass

    @abstractmethod
    async def list_all(self) -> List[Incident]:
        pass


class InMemoryIncidentRepository(IncidentRepository):
    """基于内存的故障事件仓储"""

    def __init__(self):
        self._incidents: Dict[str, Incident] = {}

    async def create(self, incident: Incident) -> Incident:
        self._incidents[incident.id] = incident
        return incident

    async def get(self, incident_id: str) -> Optional[Incident]:
        return self._incidents.get(incident_id)

    async def update(self, incident: Incident) -> Incident:
        self._incidents[incident.id] = incident
        return incident

    async def delete(self, incident_id: str) -> bool:
        if incident_id in self._incidents:
            del self._incidents[incident_id]
            return True
        return False

    async def list_all(self) -> List[Incident]:
        return list(self._incidents.values())


class FileIncidentRepository(IncidentRepository):
    """基于本地 JSON 文件的故障事件仓储"""

    def __init__(self, base_dir: Optional[str] = None):
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "incidents.json"
        self._lock = asyncio.Lock()
        self._incidents: Dict[str, Incident] = {}
        self._load_from_disk()

    async def create(self, incident: Incident) -> Incident:
        async with self._lock:
            self._incidents[incident.id] = incident
            self._persist_to_disk()
            return incident

    async def get(self, incident_id: str) -> Optional[Incident]:
        async with self._lock:
            return self._incidents.get(incident_id)

    async def update(self, incident: Incident) -> Incident:
        async with self._lock:
            self._incidents[incident.id] = incident
            self._persist_to_disk()
            return incident

    async def delete(self, incident_id: str) -> bool:
        async with self._lock:
            if incident_id not in self._incidents:
                return False
            del self._incidents[incident_id]
            self._persist_to_disk()
            return True

    async def list_all(self) -> List[Incident]:
        async with self._lock:
            return list(self._incidents.values())

    def _load_from_disk(self) -> None:
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            rows = payload.get("incidents", []) if isinstance(payload, dict) else []
            loaded: Dict[str, Incident] = {}
            for row in rows:
                try:
                    item = Incident.model_validate(row)
                    loaded[item.id] = item
                except Exception:
                    continue
            self._incidents = loaded
        except Exception:
            self._incidents = {}

    def _persist_to_disk(self) -> None:
        payload = {
            "schema_version": 1,
            "incidents": [item.model_dump(mode="json") for item in self._incidents.values()],
        }
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)
