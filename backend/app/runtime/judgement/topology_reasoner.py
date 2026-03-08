"""Topology-aware propagation scoring helpers."""

from __future__ import annotations

from typing import Any, Dict, List


def _extract_mapping_context(context: Dict[str, Any]) -> Dict[str, str]:
    """对输入执行提取mapping上下文，将原始数据整理为稳定的内部结构。"""
    assets = context.get("assets") if isinstance(context, dict) else {}
    assets = assets if isinstance(assets, dict) else {}
    mapping = assets.get("interface_mapping") if isinstance(assets.get("interface_mapping"), dict) else {}
    endpoint = mapping.get("matched_endpoint") if isinstance(mapping.get("matched_endpoint"), dict) else {}
    return {
        "service": str(endpoint.get("service") or "").strip(),
        "path": str(endpoint.get("path") or "").strip(),
        "domain": str(mapping.get("domain") or "").strip(),
        "aggregate": str(mapping.get("aggregate") or "").strip(),
        "owner_team": str(mapping.get("owner_team") or "").strip(),
    }


def score_topology_propagation(
    *,
    context: Dict[str, Any],
    evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Score evidence propagation quality using service-topology hints."""

    mapping_ctx = _extract_mapping_context(context)
    service = mapping_ctx.get("service", "")
    path = mapping_ctx.get("path", "")
    domain = mapping_ctx.get("domain", "")
    aggregate = mapping_ctx.get("aggregate", "")
    owner_team = mapping_ctx.get("owner_team", "")

    node_signals: List[str] = []
    if service:
        node_signals.append(f"service:{service}")
    if domain:
        node_signals.append(f"domain:{domain}")
    if aggregate:
        node_signals.append(f"aggregate:{aggregate}")
    if owner_team:
        node_signals.append(f"team:{owner_team}")

    propagation_hits = 0
    propagation_paths: List[str] = []
    seen_paths = set()
    for row in evidence:
        source = str(row.get("source") or "").strip() or "unknown"
        source_ref = str(row.get("source_ref") or "").strip()
        description = str(row.get("description") or "").strip()
        text = " ".join([source, source_ref, description]).lower()
        matched = False
        if path and path.lower() in text:
            matched = True
        if service and service.lower() in text:
            matched = True
        if owner_team and owner_team.lower() in text:
            matched = True
        if matched:
            propagation_hits += 1
            token = source_ref or description[:80] or source
            path_text = f"{source}->{token}"
            if path_text not in seen_paths:
                propagation_paths.append(path_text)
                seen_paths.add(path_text)

    topology_score = 0.0
    if node_signals:
        topology_score += min(0.45, len(node_signals) * 0.12)
    topology_score += min(0.55, propagation_hits * 0.1)
    return {
        "topology_score": round(max(0.0, min(1.0, topology_score)), 3),
        "node_signals": node_signals,
        "propagation_hits": propagation_hits,
        "propagation_paths": propagation_paths[:10],
    }


__all__ = ["score_topology_propagation"]
