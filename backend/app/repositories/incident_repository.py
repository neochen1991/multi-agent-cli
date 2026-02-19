"""
故障事件仓储
Incident Repository
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

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

