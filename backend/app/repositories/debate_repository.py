"""
辩论仓储
Debate Repository
"""

from abc import ABC, abstractmethod
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.models.debate import DebateResult, DebateSession


class DebateRepository(ABC):
    """辩论仓储接口"""

    @abstractmethod
    async def save_session(self, session: DebateSession) -> DebateSession:
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        pass

    @abstractmethod
    async def list_sessions(self) -> List[DebateSession]:
        pass

    @abstractmethod
    async def save_result(self, result: DebateResult) -> DebateResult:
        pass

    @abstractmethod
    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        pass


class InMemoryDebateRepository(DebateRepository):
    """基于内存的辩论仓储"""

    def __init__(self):
        self._sessions: Dict[str, DebateSession] = {}
        self._results: Dict[str, DebateResult] = {}

    async def save_session(self, session: DebateSession) -> DebateSession:
        self._sessions[session.id] = session
        return session

    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        return self._sessions.get(session_id)

    async def list_sessions(self) -> List[DebateSession]:
        return list(self._sessions.values())

    async def save_result(self, result: DebateResult) -> DebateResult:
        self._results[result.session_id] = result
        return result

    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        return self._results.get(session_id)


class FileDebateRepository(DebateRepository):
    """基于本地 JSON 文件的辩论仓储"""

    def __init__(self, base_dir: Optional[str] = None):
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "debates.json"
        self._lock = asyncio.Lock()
        self._sessions: Dict[str, DebateSession] = {}
        self._results: Dict[str, DebateResult] = {}
        self._load_from_disk()

    async def save_session(self, session: DebateSession) -> DebateSession:
        async with self._lock:
            self._sessions[session.id] = session
            self._persist_to_disk()
            return session

    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_sessions(self) -> List[DebateSession]:
        async with self._lock:
            return list(self._sessions.values())

    async def save_result(self, result: DebateResult) -> DebateResult:
        async with self._lock:
            self._results[result.session_id] = result
            self._persist_to_disk()
            return result

    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        async with self._lock:
            return self._results.get(session_id)

    def _load_from_disk(self) -> None:
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            raw_sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
            raw_results = payload.get("results", []) if isinstance(payload, dict) else []

            sessions: Dict[str, DebateSession] = {}
            for row in raw_sessions:
                try:
                    item = DebateSession.model_validate(row)
                    sessions[item.id] = item
                except Exception:
                    continue

            results: Dict[str, DebateResult] = {}
            for row in raw_results:
                try:
                    item = DebateResult.model_validate(row)
                    results[item.session_id] = item
                except Exception:
                    continue

            self._sessions = sessions
            self._results = results
        except Exception:
            self._sessions = {}
            self._results = {}

    def _persist_to_disk(self) -> None:
        payload = {
            "sessions": [item.model_dump(mode="json") for item in self._sessions.values()],
            "results": [item.model_dump(mode="json") for item in self._results.values()],
        }
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)
