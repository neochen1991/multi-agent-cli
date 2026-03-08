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
- {LOCAL_STORE_DIR}/feedback.json

使用场景：
- 记录用户对分析结果的满意度
- 收集改进建议
- 支持模型微调数据收集

Feedback Service
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings


class FeedbackService:
    """
    分析反馈持久化服务

    提供反馈记录的持久化和查询功能。

    属性：
    - _file: 反馈数据文件路径
    - _lock: 异步锁，保证并发安全

    工作流程：
    1. 用户提交反馈
    2. 自动生成 ID 和时间戳
    3. 追加到反馈列表
    4. 持久化到文件
    """

    def __init__(self) -> None:
        """
        初始化反馈服务

        创建本地反馈文件和并发写锁。
        """
        root = Path(settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "feedback.json"
        self._lock = asyncio.Lock()

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
        async with self._lock:
            items = self._load()
            items.append(record)
            self._save(items)
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
        async with self._lock:
            items = self._load()
        return list(reversed(items))[: max(1, int(limit or 100))]

    def _load(self) -> List[Dict[str, Any]]:
        """
        从文件加载反馈列表

        文件不存在或损坏时返回空列表。

        Returns:
            List[Dict[str, Any]]: 反馈列表
        """
        if not self._file.exists():
            return []
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except Exception:
            return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        """
        保存反馈列表到文件

        使用临时文件原子写入。

        Args:
            items: 反馈列表
        """
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)


# 全局实例
feedback_service = FeedbackService()