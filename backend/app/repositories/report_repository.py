"""
报告仓储
Report Repository
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ReportRepository(ABC):
    """报告仓储接口"""

    @abstractmethod
    async def save(self, report: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_latest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_latest_by_format(
        self,
        incident_id: str,
        format: str,
    ) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_by_incident(self, incident_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def save_share_token(self, token: str, incident_id: str) -> None:
        pass

    @abstractmethod
    async def get_incident_id_by_share_token(self, token: str) -> Optional[str]:
        pass


class InMemoryReportRepository(ReportRepository):
    """基于内存的报告仓储"""

    def __init__(self):
        self._reports: Dict[str, List[Dict[str, Any]]] = {}
        self._share_tokens: Dict[str, str] = {}

    async def save(self, report: Dict[str, Any]) -> Dict[str, Any]:
        incident_id = report["incident_id"]
        self._reports.setdefault(incident_id, []).append(report)
        return report

    async def get_latest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        items = self._reports.get(incident_id, [])
        return items[-1] if items else None

    async def get_latest_by_format(
        self,
        incident_id: str,
        format: str,
    ) -> Optional[Dict[str, Any]]:
        items = self._reports.get(incident_id, [])
        for item in reversed(items):
            if item.get("format") == format:
                return item
        return None

    async def list_by_incident(self, incident_id: str) -> List[Dict[str, Any]]:
        return list(self._reports.get(incident_id, []))

    async def save_share_token(self, token: str, incident_id: str) -> None:
        self._share_tokens[token] = incident_id

    async def get_incident_id_by_share_token(self, token: str) -> Optional[str]:
        return self._share_tokens.get(token)

