"""
反馈闭环服务模块

本模块提供分析结果的人工反馈持久化功能。

核心功能：
1. 保存分析结果的人工反馈
2. 为反馈学习提供持久化入口
3. 支持反馈记录查询

反馈数据结构：
{
    "id": "反馈ID",
    "created_at": "创建时间",
    ...其他反馈字段
}

存储路径：
- SQLite.feedback_items

使用场景：
- 记录用户对分析结果的满意度
- 收集改进建议
- 支持模型微调数据收集

Feedback Service
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from app.storage import sqlite_store


class FeedbackService:
    """
    分析反馈持久化服务

    提供反馈记录的持久化和查询功能。

    属性：
    - _store: SQLite 存储

    工作流程：
    1. 用户提交反馈
    2. 自动生成 ID 和时间戳
    3. 追加到反馈列表
    4. 持久化到文件
    """

    def __init__(self) -> None:
        """
        初始化反馈服务

        初始化 SQLite 反馈存储。
        """
        self._store = sqlite_store

    async def append(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        追加反馈记录

        自动生成记录 ID 和时间戳，追加到反馈列表。

        Args:
            payload: 反馈数据

        Returns:
            Dict[str, Any]: 完整的反馈记录
        """
        record = {
            "id": f"fbk_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            "created_at": datetime.utcnow().isoformat(),
            **dict(payload or {}),
        }
        # 中文注释：反馈属于结构化记录，直接落 feedback_items 表，不再写 feedback.json。
        await self._store.execute(
            """
            INSERT OR REPLACE INTO feedback_items (id, created_at, payload_json)
            VALUES (?, ?, ?)
            """,
            (record["id"], record["created_at"], self._store.dumps_json(record)),
        )
        return record

    async def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        列出反馈记录

        按时间倒序返回最近的反馈记录。

        Args:
            limit: 最大返回数量

        Returns:
            List[Dict[str, Any]]: 反馈记录列表
        """
        rows = await self._store.fetchall(
            """
            SELECT payload_json FROM feedback_items
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, int(limit or 100)),),
        )
        return [self._store.loads_json(row["payload_json"], {}) for row in rows]


# 全局实例
feedback_service = FeedbackService()
