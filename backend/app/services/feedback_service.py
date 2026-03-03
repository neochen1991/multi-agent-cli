"""Feedback loop service for RCA result review."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings


class FeedbackService:
    def __init__(self) -> None:
        root = Path(settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "feedback.json"
        self._lock = asyncio.Lock()

    async def append(self, payload: Dict[str, Any]) -> Dict[str, Any]:
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
        async with self._lock:
            items = self._load()
        return list(reversed(items))[: max(1, int(limit or 100))]

    def _load(self) -> List[Dict[str, Any]]:
        if not self._file.exists():
            return []
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except Exception:
            return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)


feedback_service = FeedbackService()

