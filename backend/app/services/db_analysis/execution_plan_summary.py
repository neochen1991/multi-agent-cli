"""Summarize execution plan hints for DatabaseAgent."""

from __future__ import annotations

from typing import Any, Dict, List


def build_execution_plan_summary(*, tool_data: Dict[str, Any], target_tables: List[str]) -> Dict[str, Any]:
    plans = [item for item in list(tool_data.get("execution_plans") or []) if isinstance(item, dict)]
    if plans:
        dominant_operators = [str(item.get("operator") or item.get("node_type") or "").strip() for item in plans]
        return {
            "available": True,
            "dominant_operators": [item for item in dominant_operators if item][:6],
            "table_hotspots": list(target_tables)[:8],
            "notes": [str(item.get("summary") or item.get("detail") or "")[:220] for item in plans[:4]],
        }
    notes = []
    for sql in list(tool_data.get("slow_sql") or [])[:4]:
        if isinstance(sql, dict):
            notes.append(str(sql.get("query") or "")[:220])
    return {
        "available": False,
        "dominant_operators": [],
        "table_hotspots": list(target_tables)[:8],
        "notes": notes,
    }
