"""Code-focused context assembler."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.code_analysis.call_graph_builder import (
    detect_resource_risk_points,
    summarize_call_graph,
    summarize_downstream_rpc,
    summarize_sql_bindings,
    summarize_transaction_boundaries,
)


def build_code_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    mapping = compact_context.get("interface_mapping") if isinstance(compact_context.get("interface_mapping"), dict) else {}
    endpoint = ((mapping.get("endpoint") or mapping.get("matched_endpoint") or {}) if isinstance(mapping, dict) else {})
    leads = service._extract_investigation_leads(compact_context, incident_context, assigned_command)  # noqa: SLF001
    tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
    if not isinstance(tool_data, dict):
        tool_data = {}
    hits = [item for item in list(tool_data.get("hits") or []) if isinstance(item, dict)]
    repo_path = str(tool_data.get("repo_path") or "").strip()
    artifact_hints = list(mapping.get("code_artifacts") or []) + list(leads.get("code_artifacts") or [])
    hit_files = [str(item.get("file") or "").strip() for item in hits if str(item.get("file") or "").strip()]
    related_files = service._expand_related_code_files(  # noqa: SLF001
        repo_path=repo_path,
        seed_files=[*artifact_hints, *hit_files],
        class_hints=list(leads.get("class_names") or []),
        depth=2,
        per_hop_limit=6,
    )
    code_windows = service._load_repo_focus_windows(  # noqa: SLF001
        repo_path=repo_path,
        candidate_files=[*artifact_hints, *hit_files, *related_files],
        max_files=8,
        max_chars=1400,
    )
    method_call_chain = service._build_method_call_chain(  # noqa: SLF001
        repo_path=repo_path,
        endpoint_interface=str(endpoint.get("interface") or ""),
        code_windows=code_windows,
        hit_snippets=[str(item.get("snippet") or "") for item in hits[:8]],
    )
    mapped_code_scope = {
        "code_artifacts": list(dict.fromkeys([str(item) for item in artifact_hints if str(item).strip()]))[:12],
        "class_names": list(leads.get("class_names") or [])[:12],
        "dependency_services": list(leads.get("dependency_services") or [])[:10],
        "database_tables": service._extract_database_tables(compact_context, incident_context, assigned_command)[:12],  # noqa: SLF001
    }
    return {
        "analysis_objective": {
            "task": str((assigned_command or {}).get("task") or "")[:240],
            "focus": str((assigned_command or {}).get("focus") or "")[:300],
            "expected_output": str((assigned_command or {}).get("expected_output") or "")[:240],
        },
        "problem_entrypoint": {
            "method": str(endpoint.get("method") or "")[:24],
            "path": str(endpoint.get("path") or "")[:240],
            "service": str(endpoint.get("service") or service._primary_service_name(compact_context, incident_context, assigned_command))[:160],  # noqa: SLF001
            "interface": str(endpoint.get("interface") or "")[:240],
        },
        "mapped_code_scope": mapped_code_scope,
        "repo_hits": {
            "keywords": list(tool_data.get("keywords") or [])[:12],
            "match_count": len(hits),
            "top_hits": hits[:12],
            "candidate_files": list(dict.fromkeys([str(item) for item in hit_files if str(item).strip()]))[:12],
            "related_files": related_files[:12],
        },
        "code_windows": code_windows,
        "method_call_chain": method_call_chain,
        "call_graph_summary": summarize_call_graph(
            method_call_chain=method_call_chain,
            mapped_code_scope=mapped_code_scope,
            code_windows=code_windows,
        ),
        "sql_binding_summary": summarize_sql_bindings(
            code_windows=code_windows,
            database_tables=list(mapped_code_scope.get("database_tables") or []),
        ),
        "downstream_rpc_summary": summarize_downstream_rpc(
            code_windows=code_windows,
            dependency_services=list(mapped_code_scope.get("dependency_services") or []),
        ),
        "resource_risk_points": detect_resource_risk_points(code_windows=code_windows),
        "transaction_boundary_summary": summarize_transaction_boundaries(
            code_windows=code_windows,
            method_call_chain=method_call_chain,
        ),
        "analysis_expectations": [
            "优先定位接口入口与事务边界，再分析同步调用、锁竞争、连接占用和重试放大。",
            "若无法形成完整调用链，至少给出入口方法、下游调用点和可疑资源占用点。",
        ],
    }
