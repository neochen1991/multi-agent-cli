"""Database-focused context assembler."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.db_analysis.execution_plan_summary import build_execution_plan_summary
from app.services.db_analysis.lock_wait_graph import build_lock_wait_graph
from app.services.db_analysis.sql_pattern_cluster import build_sql_pattern_clusters


def build_database_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
    if not isinstance(tool_data, dict):
        tool_data = {}
    target_tables = service._extract_database_tables(compact_context, incident_context, assigned_command)[:16]  # noqa: SLF001
    causal_summary = service._build_database_causal_summary(  # noqa: SLF001
        target_tables=target_tables,
        tool_data=tool_data,
    )
    return {
        "analysis_objective": {
            "task": str((assigned_command or {}).get("task") or "")[:240],
            "focus": str((assigned_command or {}).get("focus") or "")[:300],
        },
        "target_tables": target_tables,
        "schema_summary": {
            "engine": str(tool_data.get("engine") or "")[:40],
            "schema": str(tool_data.get("schema") or "")[:80],
            "tables": list(tool_data.get("tables") or [])[:16],
            "table_structures": list(tool_data.get("table_structures") or [])[:8],
            "indexes": service._trim_mapping(tool_data.get("indexes"), item_limit=8, value_limit=6),  # noqa: SLF001
        },
        "sql_signals": {
            "slow_sql": list(tool_data.get("slow_sql") or [])[:8],
            "top_sql": list(tool_data.get("top_sql") or [])[:8],
            "keyword_hits": list(tool_data.get("keyword_hits") or [])[:8],
        },
        "runtime_signals": {
            "session_status": list(tool_data.get("session_status") or [])[:8],
            "used_target_tables": bool(tool_data.get("used_target_tables")),
            "fallback_reason": str(tool_data.get("fallback_reason") or "")[:120],
        },
        "execution_plan_summary": build_execution_plan_summary(tool_data=tool_data, target_tables=target_tables),
        "lock_wait_graph": build_lock_wait_graph(tool_data=tool_data),
        "sql_pattern_clusters": build_sql_pattern_clusters(tool_data=tool_data),
        "causal_summary": causal_summary,
    }
