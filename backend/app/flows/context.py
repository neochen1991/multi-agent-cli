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
        cached = self._session_context.get(session_id)
        if cached is not None:
            return cached
        redis_value = await self._redis_get_json(f"sre:ctx:{session_id}:session")
        if redis_value:
            self._session_context[session_id] = redis_value
            return redis_value
        return {}

    async def update_session_context(self, session_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
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
        rounds = self._round_context.setdefault(session_id, [])
        item = {
            **round_context,
            "timestamp": datetime.utcnow().isoformat(),
        }
        rounds.append(item)
        await self._redis_set_json(f"sre:ctx:{session_id}:rounds", rounds)

    async def get_round_context(self, session_id: str) -> List[Dict[str, Any]]:
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
        merged = dict(base_context)
        if assets is not None:
            merged["assets"] = assets
        await self.update_session_context(session_id, merged)
        return merged

    async def snapshot(self, session_id: str) -> Dict[str, Any]:
        session_ctx = await self.get_session_context(session_id)
        round_ctx = await self.get_round_context(session_id)
        return {
            "session_context": session_ctx,
            "round_context": round_ctx,
        }

    async def _redis_set_json(self, key: str, value: Any):
        if not self._redis:
            return
        try:
            import json

            await self._redis.set(key, json.dumps(value, ensure_ascii=False), ex=settings.REDIS_CACHE_TTL)
        except Exception as e:
            logger.warning("redis_set_context_failed", key=key, error=str(e))

    async def _redis_get_json(self, key: str) -> Any:
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
