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
from app.storage import SqliteStore, sqlite_store

class ReportRepository(ABC):
    """报告仓储接口"""

    @abstractmethod
    async def save(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """保存一份报告版本。"""
        pass

    @abstractmethod
    async def get_latest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """获取指定故障最新一版报告。"""
        pass

    @abstractmethod
    async def get_latest_by_format(
        self,
        incident_id: str,
        format: str,
    ) -> Optional[Dict[str, Any]]:
        """获取指定格式的最新报告，常用于 markdown/html/pdf 回读。"""
        pass

    @abstractmethod
    async def list_by_incident(self, incident_id: str) -> List[Dict[str, Any]]:
        """列出同一故障的全部历史报告版本。"""
        pass

    @abstractmethod
    async def save_share_token(self, token: str, incident_id: str) -> None:
        """记录分享 token 到 incident 的映射关系。"""
        pass

    @abstractmethod
    async def get_incident_id_by_share_token(self, token: str) -> Optional[str]:
        """根据分享 token 反查对应 incident。"""
        pass


class InMemoryReportRepository(ReportRepository):
    """基于内存的报告仓储"""

    def __init__(self):
        """初始化内存版报告列表和分享 token 索引。"""
        self._reports: Dict[str, List[Dict[str, Any]]] = {}
        self._share_tokens: Dict[str, str] = {}

    async def save(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """执行保存，并同步更新运行时状态、持久化结果或审计轨迹。"""
        incident_id = report["incident_id"]
        self._reports.setdefault(incident_id, []).append(report)
        return report

    async def get_latest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """负责获取最新，并返回后续流程可直接消费的数据结果。"""
        items = self._reports.get(incident_id, [])
        return items[-1] if items else None

    async def get_latest_by_format(
        self,
        incident_id: str,
        format: str,
    ) -> Optional[Dict[str, Any]]:
        """负责获取最新byformat，并返回后续流程可直接消费的数据结果。"""
        items = self._reports.get(incident_id, [])
        for item in reversed(items):
            if item.get("format") == format:
                return item
        return None

    async def list_by_incident(self, incident_id: str) -> List[Dict[str, Any]]:
        """负责列出by故障，并返回后续流程可直接消费的数据结果。"""
        return list(self._reports.get(incident_id, []))

    async def save_share_token(self, token: str, incident_id: str) -> None:
        """执行保存sharetoken，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._share_tokens[token] = incident_id

    async def get_incident_id_by_share_token(self, token: str) -> Optional[str]:
        """负责获取故障idbysharetoken，并返回后续流程可直接消费的数据结果。"""
        return self._share_tokens.get(token)


class FileReportRepository(ReportRepository):
    """基于本地 JSON 文件的报告仓储"""

    def __init__(self, base_dir: Optional[str] = None):
        """初始化文件版报告仓储并恢复报告历史与分享 token。"""
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "reports.json"
        self._lock = asyncio.Lock()
        self._reports: Dict[str, List[Dict[str, Any]]] = {}
        self._share_tokens: Dict[str, str] = {}
        self._load_from_disk()

    async def save(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """执行保存，并同步更新运行时状态、持久化结果或审计轨迹。"""
        async with self._lock:
            incident_id = report["incident_id"]
            self._reports.setdefault(incident_id, []).append(report)
            self._persist_to_disk()
            return report

    async def get_latest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """负责获取最新，并返回后续流程可直接消费的数据结果。"""
        async with self._lock:
            items = self._reports.get(incident_id, [])
            return items[-1] if items else None

    async def get_latest_by_format(
        self,
        incident_id: str,
        format: str,
    ) -> Optional[Dict[str, Any]]:
        """负责获取最新byformat，并返回后续流程可直接消费的数据结果。"""
        async with self._lock:
            items = self._reports.get(incident_id, [])
            for item in reversed(items):
                if item.get("format") == format:
                    return item
            return None

    async def list_by_incident(self, incident_id: str) -> List[Dict[str, Any]]:
        """负责列出by故障，并返回后续流程可直接消费的数据结果。"""
        async with self._lock:
            return list(self._reports.get(incident_id, []))

    async def save_share_token(self, token: str, incident_id: str) -> None:
        """执行保存sharetoken，并同步更新运行时状态、持久化结果或审计轨迹。"""
        async with self._lock:
            self._share_tokens[token] = incident_id
            self._persist_to_disk()

    async def get_incident_id_by_share_token(self, token: str) -> Optional[str]:
        """负责获取故障idbysharetoken，并返回后续流程可直接消费的数据结果。"""
        async with self._lock:
            return self._share_tokens.get(token)

    def _load_from_disk(self) -> None:
        """从本地文件恢复报告和分享 token；文件损坏时退回空仓储。"""
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
        """将报告仓储完整快照写回本地文件。"""
        payload = {
            "schema_version": 1,
            "reports": self._reports,
            "share_tokens": self._share_tokens,
        }
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(self._file)


class SqliteReportRepository(ReportRepository):
    """基于 SQLite 的报告仓储。"""

    def __init__(self, store: Optional[SqliteStore] = None):
        # 中文注释：报告历史保存在 reports 表，分享链接映射保存在 share_tokens 表。
        self._store = store or sqlite_store

    async def save(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """保存一份报告版本。"""
        payload = dict(report or {})
        await self._store.execute(
            """
            INSERT INTO reports (report_id, incident_id, format, created_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("report_id") or ""),
                str(payload.get("incident_id") or ""),
                str(payload.get("format") or ""),
                str(payload.get("generated_at") or payload.get("created_at") or ""),
                self._store.dumps_json(payload),
            ),
        )
        return payload

    async def get_latest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """获取指定故障最新一版报告。"""
        row = await self._store.fetchone(
            """
            SELECT payload_json FROM reports
            WHERE incident_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (incident_id,),
        )
        if row is None:
            return None
        return self._store.loads_json(row["payload_json"], {})

    async def get_latest_by_format(
        self,
        incident_id: str,
        format: str,
    ) -> Optional[Dict[str, Any]]:
        """获取指定格式的最新报告。"""
        row = await self._store.fetchone(
            """
            SELECT payload_json FROM reports
            WHERE incident_id = ? AND format = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (incident_id, format),
        )
        if row is None:
            return None
        return self._store.loads_json(row["payload_json"], {})

    async def list_by_incident(self, incident_id: str) -> List[Dict[str, Any]]:
        """列出同一故障的全部历史报告版本。"""
        rows = await self._store.fetchall(
            """
            SELECT payload_json FROM reports
            WHERE incident_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (incident_id,),
        )
        return [self._store.loads_json(row["payload_json"], {}) for row in rows]

    async def save_share_token(self, token: str, incident_id: str) -> None:
        """记录分享 token 到 incident 的映射关系。"""
        await self._store.execute(
            """
            INSERT OR REPLACE INTO share_tokens (token, incident_id, created_at)
            VALUES (?, ?, datetime('now'))
            """,
            (token, incident_id),
        )

    async def get_incident_id_by_share_token(self, token: str) -> Optional[str]:
        """根据分享 token 反查对应 incident。"""
        row = await self._store.fetchone(
            "SELECT incident_id FROM share_tokens WHERE token = ?",
            (token,),
        )
        if row is None:
            return None
        return str(row["incident_id"] or "")
