"""Output truncation utilities."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from app.config import settings


class OutputReferenceStore:
    """Persist full outputs locally and return lightweight reference IDs."""

    def __init__(self) -> None:
        root = Path(settings.LOCAL_STORE_DIR)
        self._dir = root / "output_refs"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, ref_id: str) -> Path:
        return self._dir / f"{ref_id}.json"

    def save(
        self,
        *,
        content: str,
        session_id: str = "",
        category: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> str:
        ref_id = f"out_{uuid4().hex[:16]}"
        payload = {
            "ref_id": ref_id,
            "session_id": str(session_id or ""),
            "category": str(category or ""),
            "content": str(content or ""),
            "metadata": dict(metadata or {}),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        self._path(ref_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return ref_id

    def load(self, ref_id: str) -> Dict[str, Any] | None:
        path = self._path(ref_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        return data


output_reference_store = OutputReferenceStore()


def truncate_text(
    value: str,
    *,
    max_chars: int = 2400,
    session_id: str = "",
    category: str = "",
    metadata: Dict[str, Any] | None = None,
) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    ref_id = output_reference_store.save(
        content=text,
        session_id=session_id,
        category=category,
        metadata=metadata,
    )
    return f"{text[:max_chars]}...(truncated,{len(text)} chars, ref={ref_id})"


def truncate_payload(
    payload: Dict[str, Any],
    *,
    max_chars: int = 1800,
    session_id: str = "",
    category: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    refs: Dict[str, str] = {}
    for key, value in (payload or {}).items():
        if isinstance(value, str):
            text = str(value or "")
            if len(text) > max_chars:
                ref_id = output_reference_store.save(
                    content=text,
                    session_id=session_id,
                    category=category or "payload",
                    metadata={"field": key, **dict(metadata or {})},
                )
                refs[key] = ref_id
                result[key] = f"{text[:max_chars]}...(truncated,{len(text)} chars, ref={ref_id})"
            else:
                result[key] = text
        elif isinstance(value, list):
            result[key] = value[:20]
        else:
            result[key] = value
    if refs:
        result["_output_refs"] = refs
    return result


def get_output_reference(ref_id: str) -> Dict[str, Any] | None:
    return output_reference_store.load(ref_id)
