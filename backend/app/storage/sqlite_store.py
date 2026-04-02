"""
统一 SQLite 存储基础设施。

负责：
1. 初始化数据库文件与表结构
2. 提供基础 execute/fetchone/fetchall 能力
3. 统一 JSON 序列化/反序列化
4. 用异步锁保护当前进程内的并发写入
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from app.config import settings


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS incidents (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS debate_sessions (
        id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        status TEXT NOT NULL,
        phase TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS debate_results (
        session_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id TEXT,
        incident_id TEXT NOT NULL,
        format TEXT,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reports_incident_created_at
    ON reports (incident_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reports_incident_format_created_at
    ON reports (incident_id, format, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS share_tokens (
        token TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_sessions (
        session_id TEXT PRIMARY KEY,
        trace_id TEXT NOT NULL,
        status TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        event_type TEXT,
        agent_name TEXT,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_runtime_events_session_id
    ON runtime_events (session_id, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_tasks (
        session_id TEXT PRIMARY KEY,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lineage_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_lineage_events_session_id
    ON lineage_events (session_id, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_items (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS remediation_actions (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS monitor_targets (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        enabled INTEGER NOT NULL,
        check_interval_sec INTEGER NOT NULL,
        timeout_sec INTEGER NOT NULL,
        cooldown_sec INTEGER NOT NULL,
        last_checked_at TEXT,
        last_triggered_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_monitor_targets_enabled
    ON monitor_targets (enabled, updated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS monitor_scan_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_monitor_scan_events_target_id
    ON monitor_scan_events (target_id, id DESC)
    """,
)


def _default_sqlite_path() -> str:
    """返回结构化存储默认 SQLite 路径。"""
    configured = str(getattr(settings, "LOCAL_STORE_SQLITE_PATH", "") or "").strip()
    if configured:
        return configured
    return str(Path(settings.LOCAL_STORE_DIR) / "app.db")


class SqliteStore:
    """封装统一 SQLite 数据库操作。"""

    def __init__(self, db_path: Optional[str] = None):
        # 中文注释：所有结构化持久化共享同一数据库文件，避免多事实源。
        self._db_path = Path(db_path or _default_sqlite_path())
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        """返回数据库文件路径。"""
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        """创建带 Row 工厂的 SQLite 连接。"""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        """初始化数据库表结构。"""
        with self._connect() as conn:
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)
            conn.commit()

    async def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        """执行写入类 SQL。"""
        async with self._lock:
            with self._connect() as conn:
                conn.execute(sql, tuple(params or ()))
                conn.commit()

    async def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        """批量执行写入类 SQL。"""
        async with self._lock:
            with self._connect() as conn:
                conn.executemany(sql, list(rows))
                conn.commit()

    async def fetchone(self, sql: str, params: Sequence[Any] | None = None) -> Optional[sqlite3.Row]:
        """查询单行结果。"""
        async with self._lock:
            with self._connect() as conn:
                cur = conn.execute(sql, tuple(params or ()))
                return cur.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[sqlite3.Row]:
        """查询多行结果。"""
        async with self._lock:
            with self._connect() as conn:
                cur = conn.execute(sql, tuple(params or ()))
                return list(cur.fetchall())

    @staticmethod
    def dumps_json(payload: Any) -> str:
        """统一 JSON 序列化，兼容 datetime 与 Pydantic 输出。"""
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def loads_json(text: Any, default: Any) -> Any:
        """统一 JSON 反序列化，异常时回退默认值。"""
        try:
            return json.loads(str(text or ""))
        except Exception:
            return default


sqlite_store = SqliteStore()


__all__ = ["SqliteStore", "sqlite_store", "SCHEMA_STATEMENTS"]
