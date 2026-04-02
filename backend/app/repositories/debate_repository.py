"""
辩论仓储模块

本模块提供辩论会话和结果的数据持久化层。

核心功能：
1. 辩论会话的 CRUD 操作
2. 辩论结果的存储和查询
3. 支持内存存储和 SQLite 存储两种后端

存储后端：
- InMemoryDebateRepository: 内存存储，适合测试
- SqliteDebateRepository: SQLite 存储，适合单机部署

存储结构：
- {LOCAL_STORE_DIR}/debates.json

使用场景：
- DebateService 通过此模块持久化辩论数据
- 支持会话状态恢复和结果查询

Debate Repository
"""

from abc import ABC, abstractmethod
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.models.debate import DebateResult, DebateSession
from app.storage import SqliteStore, sqlite_store


class DebateRepository(ABC):
    """
    辩论仓储接口

    定义辩论会话和结果持久化的标准接口。

    方法：
    - save_session: 保存会话
    - get_session: 获取会话
    - list_sessions: 列出所有会话
    - save_result: 保存结果
    - get_result: 获取结果
    """

    @abstractmethod
    async def save_session(self, session: DebateSession) -> DebateSession:
        """
        保存辩论会话

        Args:
            session: 辩论会话对象

        Returns:
            DebateSession: 保存的会话
        """
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        """
        获取辩论会话

        Args:
            session_id: 会话 ID

        Returns:
            Optional[DebateSession]: 会话对象，不存在则返回 None
        """
        pass

    @abstractmethod
    async def list_sessions(self) -> List[DebateSession]:
        """
        列出所有辩论会话

        Returns:
            List[DebateSession]: 会话列表
        """
        pass

    @abstractmethod
    async def save_result(self, result: DebateResult) -> DebateResult:
        """
        保存辩论结果

        Args:
            result: 辩论结果对象

        Returns:
            DebateResult: 保存的结果
        """
        pass

    @abstractmethod
    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        """
        获取辩论结果

        Args:
            session_id: 会话 ID

        Returns:
            Optional[DebateResult]: 结果对象，不存在则返回 None
        """
        pass


class InMemoryDebateRepository(DebateRepository):
    """
    基于内存的辩论仓储

    适合测试环境或无需持久化的场景。
    数据仅在进程生命周期内有效。

    属性：
    - _sessions: 会话字典（ID -> DebateSession）
    - _results: 结果字典（session_id -> DebateResult）
    """

    def __init__(self):
        """
        初始化内存仓储

        创建空的会话和结果字典。
        """
        self._sessions: Dict[str, DebateSession] = {}
        self._results: Dict[str, DebateResult] = {}

    async def save_session(self, session: DebateSession) -> DebateSession:
        """
        保存辩论会话

        Args:
            session: 辩论会话对象

        Returns:
            DebateSession: 保存的会话
        """
        self._sessions[session.id] = session
        return session

    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        """
        获取辩论会话

        Args:
            session_id: 会话 ID

        Returns:
            Optional[DebateSession]: 会话对象
        """
        return self._sessions.get(session_id)

    async def list_sessions(self) -> List[DebateSession]:
        """
        列出所有辩论会话

        Returns:
            List[DebateSession]: 会话列表
        """
        return list(self._sessions.values())

    async def save_result(self, result: DebateResult) -> DebateResult:
        """
        保存辩论结果

        Args:
            result: 辩论结果对象

        Returns:
            DebateResult: 保存的结果
        """
        self._results[result.session_id] = result
        return result

    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        """
        获取辩论结果

        Args:
            session_id: 会话 ID

        Returns:
            Optional[DebateResult]: 结果对象
        """
        return self._results.get(session_id)


class FileDebateRepository(DebateRepository):
    """
    基于本地 JSON 文件的辩论仓储

    适合单机部署，支持持久化。
    使用原子写入保证数据安全。

    存储路径：
    - {LOCAL_STORE_DIR}/debates.json

    属性：
    - _file: 数据文件路径
    - _lock: 异步锁，保证并发安全
    - _sessions: 会话字典（内存缓存）
    - _results: 结果字典（内存缓存）
    """

    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化文件仓储

        创建存储目录，并从磁盘加载已有数据。

        Args:
            base_dir: 基础存储目录，未提供则使用配置值
        """
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "debates.json"
        self._lock = asyncio.Lock()
        self._sessions: Dict[str, DebateSession] = {}
        self._results: Dict[str, DebateResult] = {}
        self._load_from_disk()

    async def save_session(self, session: DebateSession) -> DebateSession:
        """
        保存辩论会话（持久化）

        Args:
            session: 辩论会话对象

        Returns:
            DebateSession: 保存的会话
        """
        async with self._lock:
            self._sessions[session.id] = session
            self._persist_to_disk()
        return session

    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        """
        获取辩论会话

        Args:
            session_id: 会话 ID

        Returns:
            Optional[DebateSession]: 会话对象
        """
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_sessions(self) -> List[DebateSession]:
        """
        列出所有辩论会话

        Returns:
            List[DebateSession]: 会话列表
        """
        async with self._lock:
            return list(self._sessions.values())

    async def save_result(self, result: DebateResult) -> DebateResult:
        """
        保存辩论结果（持久化）

        Args:
            result: 辩论结果对象

        Returns:
            DebateResult: 保存的结果
        """
        async with self._lock:
            self._results[result.session_id] = result
            self._persist_to_disk()
        return result

    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        """
        获取辩论结果

        Args:
            session_id: 会话 ID

        Returns:
            Optional[DebateResult]: 结果对象
        """
        async with self._lock:
            return self._results.get(session_id)

    def _load_from_disk(self) -> None:
        """
        从磁盘加载数据

        启动时从 JSON 文件恢复会话和结果数据。
        无效记录会被跳过。
        """
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
        """
        持久化到磁盘

        使用临时文件原子写入，避免进程中断导致数据损坏。
        """
        payload = {
            "schema_version": 1,
            "sessions": [item.model_dump(mode="json") for item in self._sessions.values()],
            "results": [item.model_dump(mode="json") for item in self._results.values()],
        }
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)


class SqliteDebateRepository(DebateRepository):
    """基于 SQLite 的辩论仓储。"""

    def __init__(self, store: Optional[SqliteStore] = None):
        # 中文注释：会话与结果分表存储，便于独立查询和后续治理统计。
        self._store = store or sqlite_store

    async def save_session(self, session: DebateSession) -> DebateSession:
        """保存辩论会话。"""
        payload = session.model_dump(mode="json")
        await self._store.execute(
            """
            INSERT OR REPLACE INTO debate_sessions
            (id, incident_id, status, phase, created_at, updated_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.incident_id,
                str(session.status.value if hasattr(session.status, "value") else session.status),
                str(session.current_phase.value if getattr(session.current_phase, "value", None) else session.current_phase or ""),
                str(payload.get("created_at") or ""),
                str(payload.get("updated_at") or ""),
                self._store.dumps_json(payload),
            ),
        )
        return session

    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        """获取辩论会话。"""
        row = await self._store.fetchone(
            "SELECT payload_json FROM debate_sessions WHERE id = ?",
            (session_id,),
        )
        if row is None:
            return None
        return DebateSession.model_validate(self._store.loads_json(row["payload_json"], {}))

    async def list_sessions(self) -> List[DebateSession]:
        """列出所有辩论会话。"""
        rows = await self._store.fetchall(
            "SELECT payload_json FROM debate_sessions ORDER BY created_at DESC, id DESC"
        )
        return [
            DebateSession.model_validate(self._store.loads_json(row["payload_json"], {}))
            for row in rows
        ]

    async def save_result(self, result: DebateResult) -> DebateResult:
        """保存辩论结果。"""
        payload = result.model_dump(mode="json")
        await self._store.execute(
            """
            INSERT OR REPLACE INTO debate_results
            (session_id, incident_id, created_at, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                result.session_id,
                result.incident_id,
                str(payload.get("created_at") or ""),
                self._store.dumps_json(payload),
            ),
        )
        return result

    async def get_result(self, session_id: str) -> Optional[DebateResult]:
        """获取辩论结果。"""
        row = await self._store.fetchone(
            "SELECT payload_json FROM debate_results WHERE session_id = ?",
            (session_id,),
        )
        if row is None:
            return None
        return DebateResult.model_validate(self._store.loads_json(row["payload_json"], {}))
