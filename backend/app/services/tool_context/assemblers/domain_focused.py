"""Domain-focused context assembler."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.domain_analysis.constraint_checks import (
    build_aggregate_invariants,
    build_domain_constraint_checks,
)


def build_domain_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    mapping = compact_context.get("interface_mapping") if isinstance(compact_context.get("interface_mapping"), dict) else {}
    tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
    if not isinstance(tool_data, dict):
        tool_data = {}
    matches = [item for item in list(tool_data.get("matches") or []) if isinstance(item, dict)]
    endpoint = ((mapping.get("endpoint") or mapping.get("matched_endpoint") or {}) if isinstance(mapping, dict) else {})
    causal_summary = service._build_domain_causal_summary(  # noqa: SLF001
        mapping=mapping if isinstance(mapping, dict) else {},
        endpoint=endpoint if isinstance(endpoint, dict) else {},
        matches=matches[:8],
    )
    return {
        "responsibility_mapping": {
            "matched": bool(mapping.get("matched")),
            "confidence": mapping.get("confidence"),
            "domain": str(mapping.get("domain") or "")[:120],
            "aggregate": str(mapping.get("aggregate") or "")[:120],
            "owner_team": str(mapping.get("owner_team") or "")[:120],
            "owner": str(mapping.get("owner") or "")[:120],
            "feature": str(mapping.get("feature") or "")[:120],
        },
        "interface_scope": {
            "method": str(endpoint.get("method") or "")[:24],
            "path": str(endpoint.get("path") or "")[:240],
            "service": str(endpoint.get("service") or service._primary_service_name(compact_context, incident_context, assigned_command))[:160],  # noqa: SLF001
            "database_tables": list(mapping.get("database_tables") or mapping.get("db_tables") or [])[:12],
            "dependency_services": list(mapping.get("dependency_services") or [])[:10],
            "monitor_items": list(mapping.get("monitor_items") or [])[:10],
        },
        "knowledge_matches": matches[:8],
        "cmdb_payload": (((tool_data.get("remote_cmdb") or {}).get("payload") or {}) if isinstance(tool_data.get("remote_cmdb"), dict) else {}),
        "aggregate_invariants": build_aggregate_invariants(
            mapping=mapping if isinstance(mapping, dict) else {},
            endpoint=endpoint if isinstance(endpoint, dict) else {},
        ),
        "domain_constraint_checks": build_domain_constraint_checks(
            mapping=mapping if isinstance(mapping, dict) else {},
            endpoint=endpoint if isinstance(endpoint, dict) else {},
            matches=matches[:8],
        ),
        "causal_summary": causal_summary,
    }
