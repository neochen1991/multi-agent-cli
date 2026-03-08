"""
审计轨迹记录器模块

本模块提供审计轨迹的记录和查询功能。

核心功能：
1. 追加审计记录（事件、Agent、工具调用）
2. 读取会话轨迹
3. 生成轨迹摘要

存储设计：
- 基于 JSONL 格式，追加写入
- 每个会话一个文件
- 支持按时间排序读取

使用场景：
- 事件分发时记录轨迹
- 问题排查时查询历史
- 性能分析时统计耗时

Lineage recorder for runtime event/agent/tool tracking.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.runtime.trace_lineage.models import LineageRecord


class LineageRecorder:
    """
    基于文件的审计轨迹记录器

    无需外部数据库，使用本地文件系统存储审计轨迹。

    存储路径：
    - {LOCAL_STORE_DIR}/lineage/{session_id}.jsonl

    属性：
    - _root: 轨迹存储根目录
    - _lock: 异步锁，保证并发安全
    - _seq_by_session: 各会话的序号计数器

    特点：
    - 追加写入，不影响已有数据
    - 序号自动递增
    - 支持并发写入
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        """
        初始化审计轨迹记录器

        创建轨迹存储目录。

        Args:
            base_dir: 基础存储目录，未提供则使用配置值
        """
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        self._root = root / "lineage"
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._seq_by_session: Dict[str, int] = {}

    def _file(self, session_id: str) -> Path:
        """
        获取会话轨迹文件路径

        Args:
            session_id: 会话 ID

        Returns:
            Path: 轨迹文件路径
        """
        return self._root / f"{session_id}.jsonl"

    def _next_seq(self, session_id: str) -> int:
        """
        获取下一个序号

        序号在会话内递增，用于排序。

        Args:
            session_id: 会话 ID

        Returns:
            int: 下一个序号
        """
        current = int(self._seq_by_session.get(session_id, 0)) + 1
        self._seq_by_session[session_id] = current
        return current

    async def append(
        self,
        *,
        session_id: str,
        kind: str,
        trace_id: str = "",
        phase: str = "",
        agent_name: str = "",
        event_type: str = "",
        confidence: float = 0.0,
        duration_ms: float = 0.0,
        input_summary: Optional[Dict[str, Any]] = None,
        output_summary: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> LineageRecord:
        """
        追加审计记录

        创建并持久化一条审计轨迹记录。

        Args:
            session_id: 会话 ID
            kind: 记录类型（session/event/agent/tool/summary）
            trace_id: 追踪 ID
            phase: 执行阶段
            agent_name: Agent 名称
            event_type: 事件类型
            confidence: 置信度（0-1）
            duration_ms: 执行耗时（毫秒）
            input_summary: 输入摘要
            output_summary: 输出摘要
            tool_calls: 工具调用列表
            payload: 原始数据

        Returns:
            LineageRecord: 创建的审计记录
        """
        record = LineageRecord(
            session_id=session_id,
            trace_id=trace_id,
            seq=self._next_seq(session_id),
            kind=kind,  # type: ignore[arg-type]
            timestamp=datetime.utcnow(),
            phase=phase,
            agent_name=agent_name,
            event_type=event_type,
            confidence=max(0.0, min(1.0, float(confidence or 0.0))),
            duration_ms=max(0.0, float(duration_ms or 0.0)),
            input_summary=input_summary or {},
            output_summary=output_summary or {},
            tool_calls=tool_calls or [],
            payload=payload or {},
        )

        # 追加写入 JSONL 文件
        line = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, default=str)
        async with self._lock:
            with self._file(session_id).open("a", encoding="utf-8") as fp:
                fp.write(line)
                fp.write("\n")

        return record

    async def read(self, session_id: str) -> List[LineageRecord]:
        """
        读取会话轨迹

        读取指定会话的所有审计记录，按序号排序。

        Args:
            session_id: 会话 ID

        Returns:
            List[LineageRecord]: 审计记录列表
        """
        path = self._file(session_id)
        if not path.exists():
            return []

        rows: List[LineageRecord] = []
        async with self._lock:
            for line in path.read_text(encoding="utf-8").splitlines():
                text = str(line or "").strip()
                if not text:
                    continue
                try:
                    rows.append(LineageRecord.model_validate(json.loads(text)))
                except Exception:
                    continue

        # 按序号和时间戳排序
        rows.sort(key=lambda item: (item.seq, item.timestamp))

        # 更新序号计数器
        if rows:
            self._seq_by_session[session_id] = max(
                self._seq_by_session.get(session_id, 0),
                rows[-1].seq
            )

        return rows

    async def summarize(self, session_id: str) -> Dict[str, Any]:
        """
        生成轨迹摘要

        统计会话的审计记录数量、Agent 列表、事件数、工具调用数等。

        Args:
            session_id: 会话 ID

        Returns:
            Dict[str, Any]: 摘要信息
        """
        rows = await self.read(session_id)
        if not rows:
            return {"session_id": session_id, "records": 0, "agents": [], "events": 0, "tools": 0}

        # 提取唯一的 Agent 名称
        agents = sorted({row.agent_name for row in rows if row.agent_name})

        # 统计各类型记录数
        event_rows = [row for row in rows if row.kind == "event"]
        tool_rows = [row for row in rows if row.kind == "tool"]

        return {
            "session_id": session_id,
            "records": len(rows),
            "events": len(event_rows),
            "tools": len(tool_rows),
            "agents": agents,
            "first_ts": rows[0].timestamp.isoformat(),
            "last_ts": rows[-1].timestamp.isoformat(),
        }


# 全局实例
lineage_recorder = LineageRecorder()