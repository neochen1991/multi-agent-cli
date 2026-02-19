"""
辩论仓储
Debate Repository
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

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

