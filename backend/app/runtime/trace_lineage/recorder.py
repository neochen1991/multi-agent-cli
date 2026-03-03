"""Lineage recorder for runtime event/agent/tool tracking."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.runtime.trace_lineage.models import LineageRecord


class LineageRecorder:
    """File-based lineage recorder (no external DB)."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        self._root = root / "lineage"
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._seq_by_session: Dict[str, int] = {}

    def _file(self, session_id: str) -> Path:
        return self._root / f"{session_id}.jsonl"

    def _next_seq(self, session_id: str) -> int:
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
        line = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, default=str)
        async with self._lock:
            with self._file(session_id).open("a", encoding="utf-8") as fp:
                fp.write(line)
                fp.write("\n")
        return record

    async def read(self, session_id: str) -> List[LineageRecord]:
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
        rows.sort(key=lambda item: (item.seq, item.timestamp))
        if rows:
            self._seq_by_session[session_id] = max(self._seq_by_session.get(session_id, 0), rows[-1].seq)
        return rows

    async def summarize(self, session_id: str) -> Dict[str, Any]:
        rows = await self.read(session_id)
        if not rows:
            return {"session_id": session_id, "records": 0, "agents": [], "events": 0, "tools": 0}
        agents = sorted({row.agent_name for row in rows if row.agent_name})
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


lineage_recorder = LineageRecorder()

