"""Normalize mixed evidence payload into standard EvidenceItem dicts."""

from __future__ import annotations

from typing import Any, Dict, List


def normalize_evidence_items(raw_items: Any) -> List[Dict[str, Any]]:
    items = raw_items if isinstance(raw_items, list) else []
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, dict):
            evidence_id = str(item.get("evidence_id") or f"evd_{index}")
            source = str(item.get("source") or "ai_debate")
            source_ref = str(item.get("source_ref") or "")
            description = str(
                item.get("description")
                or item.get("evidence")
                or item.get("summary")
                or ""
            ).strip()
            category = str(item.get("type") or "unknown")
            strength = str(item.get("strength") or "medium")
            if strength not in {"strong", "medium", "weak"}:
                strength = "medium"
            normalized.append(
                {
                    "evidence_id": evidence_id,
                    "type": category,
                    "description": description,
                    "source": source,
                    "source_ref": source_ref or None,
                    "location": item.get("location") or item.get("code_location"),
                    "strength": strength,
                }
            )
        else:
            text = str(item or "").strip()
            if text:
                normalized.append(
                    {
                        "evidence_id": f"evd_{index}",
                        "type": "text",
                        "description": text,
                        "source": "ai_debate",
                        "source_ref": None,
                        "location": None,
                        "strength": "medium",
                    }
                )
    return normalized

