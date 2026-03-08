"""
辩论上下文管理
Debate Context Manager
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.config import settings

logger = structlog.get_logger()


class ContextManager:
    """管理辩论会话上下文（会话、资产、轮次）"""

    def __init__(self):
        """初始化内存缓存，并在配置开启时接入 Redis 作为可选外部上下文存储。"""
        self._session_context: Dict[str, Dict[str, Any]] = {}
        self._round_context: Dict[str, List[Dict[str, Any]]] = {}
        self._redis = None
        if settings.ENABLE_REDIS_CONTEXT:
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            except Exception as e:
                logger.warning("redis_context_disabled", error=str(e))

    async def init_session_context(self, session_id: str, context: Dict[str, Any]) -> None:
        """初始化某个会话的上下文快照，并同步写入 Redis 缓存。"""
        payload = {
            **context,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._session_context[session_id] = payload
        self._round_context[session_id] = []
        await self._redis_set_json(f"sre:ctx:{session_id}:session", payload)
        await self._redis_set_json(f"sre:ctx:{session_id}:rounds", [])

    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """读取会话级上下文，优先内存缓存，其次 Redis。"""
        cached = self._session_context.get(session_id)
        if cached is not None:
            return cached
        redis_value = await self._redis_get_json(f"sre:ctx:{session_id}:session")
        if redis_value:
            self._session_context[session_id] = redis_value
            return redis_value
        return {}

    async def update_session_context(self, session_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """对现有会话上下文做增量更新，并刷新更新时间。"""
        current = self._session_context.setdefault(session_id, {})
        current.update(patch)
        current["updated_at"] = datetime.utcnow().isoformat()
        await self._redis_set_json(f"sre:ctx:{session_id}:session", current)
        return current

    async def append_round_context(
        self,
        session_id: str,
        round_context: Dict[str, Any],
    ) -> None:
        """向某个会话追加一条轮次级上下文记录。"""
        rounds = self._round_context.setdefault(session_id, [])
        item = {
            **round_context,
            "timestamp": datetime.utcnow().isoformat(),
        }
        rounds.append(item)
        await self._redis_set_json(f"sre:ctx:{session_id}:rounds", rounds)

    async def get_round_context(self, session_id: str) -> List[Dict[str, Any]]:
        """读取某个会话的所有轮次上下文，优先内存缓存，其次 Redis。"""
        cached = self._round_context.get(session_id)
        if cached is not None:
            return list(cached)
        redis_value = await self._redis_get_json(f"sre:ctx:{session_id}:rounds")
        if isinstance(redis_value, list):
            self._round_context[session_id] = redis_value
            return list(redis_value)
        return []

    async def build_debate_context(
        self,
        session_id: str,
        base_context: Dict[str, Any],
        assets: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """把基础上下文和资产快照合并成辩论阶段真正使用的上下文。"""
        merged = dict(base_context)
        if assets is not None:
            merged["assets"] = assets
        await self.update_session_context(session_id, merged)
        return merged

    async def snapshot(self, session_id: str) -> Dict[str, Any]:
        """返回会话上下文和轮次上下文的完整快照，供调试或回放使用。"""
        session_ctx = await self.get_session_context(session_id)
        round_ctx = await self.get_round_context(session_id)
        return {
            "session_context": session_ctx,
            "round_context": round_ctx,
        }

    async def _redis_set_json(self, key: str, value: Any):
        """把任意对象序列化为 JSON 并写入 Redis。"""
        if not self._redis:
            return
        try:
            import json

            await self._redis.set(key, json.dumps(value, ensure_ascii=False), ex=settings.REDIS_CACHE_TTL)
        except Exception as e:
            logger.warning("redis_set_context_failed", key=key, error=str(e))

    async def _redis_get_json(self, key: str) -> Any:
        """从 Redis 读取 JSON 并反序列化成 Python 对象。"""
        if not self._redis:
            return None
        try:
            import json

            raw = await self._redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("redis_get_context_failed", key=key, error=str(e))
        return None


context_manager = ContextManager()
