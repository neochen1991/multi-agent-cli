"""
报告仓储
Report Repository
"""

from abc import ABC, abstractmethod
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

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


class FileReportRepository(ReportRepository):
    """基于本地 JSON 文件的报告仓储"""

    def __init__(self, base_dir: Optional[str] = None):
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "reports.json"
        self._lock = asyncio.Lock()
        self._reports: Dict[str, List[Dict[str, Any]]] = {}
        self._share_tokens: Dict[str, str] = {}
        self._load_from_disk()

    async def save(self, report: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            incident_id = report["incident_id"]
            self._reports.setdefault(incident_id, []).append(report)
            self._persist_to_disk()
            return report

    async def get_latest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            items = self._reports.get(incident_id, [])
            return items[-1] if items else None

    async def get_latest_by_format(
        self,
        incident_id: str,
        format: str,
    ) -> Optional[Dict[str, Any]]:
        async with self._lock:
            items = self._reports.get(incident_id, [])
            for item in reversed(items):
                if item.get("format") == format:
                    return item
            return None

    async def list_by_incident(self, incident_id: str) -> List[Dict[str, Any]]:
        async with self._lock:
            return list(self._reports.get(incident_id, []))

    async def save_share_token(self, token: str, incident_id: str) -> None:
        async with self._lock:
            self._share_tokens[token] = incident_id
            self._persist_to_disk()

    async def get_incident_id_by_share_token(self, token: str) -> Optional[str]:
        async with self._lock:
            return self._share_tokens.get(token)

    def _load_from_disk(self) -> None:
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            reports = payload.get("reports", {}) if isinstance(payload, dict) else {}
            share_tokens = payload.get("share_tokens", {}) if isinstance(payload, dict) else {}
            self._reports = reports if isinstance(reports, dict) else {}
            self._share_tokens = share_tokens if isinstance(share_tokens, dict) else {}
        except Exception:
            self._reports = {}
            self._share_tokens = {}

    def _persist_to_disk(self) -> None:
        payload = {
            "reports": self._reports,
            "share_tokens": self._share_tokens,
        }
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(self._file)
