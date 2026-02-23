"""
Local runtime session checkpoint store.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from app.runtime.messages import RuntimeState, RoundCheckpoint, FinalVerdict


class RuntimeSessionStore:
    """File-based runtime checkpoint/event store (no external DB)."""

    def __init__(self, base_dir: Optional[str] = None):
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        self._root = root / "runtime"
        self._state_dir = self._root / "sessions"
        self._events_dir = self._root / "events"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._events_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _state_path(self, session_id: str) -> Path:
        return self._state_dir / f"{session_id}.json"

    def _events_path(self, session_id: str) -> Path:
        return self._events_dir / f"{session_id}.jsonl"

    async def create(
        self,
        session_id: str,
        trace_id: str,
        context_summary: Dict[str, Any],
    ) -> RuntimeState:
        state = RuntimeState(
            session_id=session_id,
            trace_id=trace_id,
            status="running",
            context_summary=context_summary,
        )
        await self._save_state(state)
        return state

    async def load(self, session_id: str) -> Optional[RuntimeState]:
        async with self._lock:
            path = self._state_path(session_id)
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            return RuntimeState.model_validate(payload)

    async def append_round(self, session_id: str, checkpoint: RoundCheckpoint) -> None:
        async with self._lock:
            state = self._load_state_locked(session_id)
            if not state:
                return
            state.rounds.append(checkpoint)
            state.updated_at = datetime.utcnow()
            await self._save_state_locked(state)

    async def complete(self, session_id: str, verdict: FinalVerdict) -> None:
        async with self._lock:
            state = self._load_state_locked(session_id)
            if not state:
                return
            state.final_verdict = verdict
            state.status = "completed"
            state.updated_at = datetime.utcnow()
            await self._save_state_locked(state)

    async def fail(self, session_id: str) -> None:
        async with self._lock:
            state = self._load_state_locked(session_id)
            if not state:
                return
            state.status = "failed"
            state.updated_at = datetime.utcnow()
            await self._save_state_locked(state)

    async def append_event(self, session_id: str, event: Dict[str, Any]) -> None:
        async with self._lock:
            path = self._events_path(session_id)
            line = json.dumps(event, ensure_ascii=False, default=str)
            with path.open("a", encoding="utf-8") as fp:
                fp.write(line)
                fp.write("\n")

    async def _save_state(self, state: RuntimeState) -> None:
        async with self._lock:
            await self._save_state_locked(state)

    def _load_state_locked(self, session_id: str) -> Optional[RuntimeState]:
        path = self._state_path(session_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeState.model_validate(payload)

    async def _save_state_locked(self, state: RuntimeState) -> None:
        path = self._state_path(state.session_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)


runtime_session_store = RuntimeSessionStore()
