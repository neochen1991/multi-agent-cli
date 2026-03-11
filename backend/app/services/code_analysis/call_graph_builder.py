"""Method-call chain and topology summaries for CodeAgent."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.code_analysis.source_loader import find_source_unit, guess_entry_method, load_source_units


def build_method_call_chain(
    *,
    repo_path: str,
    endpoint_interface: str,
    code_windows: List[Dict[str, Any]],
    hit_snippets: List[str],
) -> List[Dict[str, Any]]:
    root = Path(str(repo_path or "").strip())
    if not root.exists() or not root.is_dir():
        return []
    parsed = parse_interface_ref(endpoint_interface)
    files = [str(item.get("file") or "").strip() for item in code_windows if str(item.get("file") or "").strip()]
    source_units = load_source_units(root, files[:8])
    if not source_units:
        return []

    entry_symbol = parsed.get("symbol") or source_units[0].get("symbol") or ""
    entry_method = parsed.get("method") or guess_entry_method(source_units, hit_snippets)
    if not entry_method:
        return []
    start_unit = find_source_unit(source_units, entry_symbol, preferred_file=files[0] if files else "")
    if not start_unit:
        start_unit = source_units[0]
    chain: List[Dict[str, Any]] = []
    visited: set[str] = set()
    current_symbol = str(start_unit.get("symbol") or "")
    current_method = entry_method
    for _ in range(6):
        unit = find_source_unit(source_units, current_symbol)
        if not unit:
            break
        methods = unit.get("methods") if isinstance(unit.get("methods"), dict) else {}
        method_meta = methods.get(current_method) if isinstance(methods, dict) else None
        if not isinstance(method_meta, dict):
            if not methods:
                break
            fallback_name, fallback_meta = next(iter(methods.items()))
            current_method = str(fallback_name)
            method_meta = fallback_meta if isinstance(fallback_meta, dict) else {}
        key = f"{current_symbol}#{current_method}"
        if key in visited:
            break
        visited.add(key)
        chain.append(
            {
                "symbol": current_symbol,
                "method": current_method,
                "file": str(unit.get("file") or ""),
                "line": int(method_meta.get("line") or 0),
                "snippet": str(method_meta.get("snippet") or "")[:220],
            }
        )
        next_call = resolve_next_method_call(
            source_units=source_units,
            current_unit=unit,
            method_meta=method_meta,
        )
        if not next_call:
            break
        current_symbol = str(next_call.get("symbol") or "")
        current_method = str(next_call.get("method") or "")
        if not current_symbol or not current_method:
            break
    return chain


def parse_interface_ref(raw: str) -> Dict[str, str]:
    text = str(raw or "").strip()
    if not text:
        return {"symbol": "", "method": ""}
    for sep in ("#", ".", "::"):
        if sep in text:
            left, right = text.split(sep, 1)
            return {"symbol": left.strip(), "method": right.strip()}
    return {"symbol": text.strip(), "method": ""}


def resolve_next_method_call(
    *,
    source_units: List[Dict[str, Any]],
    current_unit: Dict[str, Any],
    method_meta: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    snippet = str(method_meta.get("snippet") or "")
    fields = current_unit.get("fields") if isinstance(current_unit.get("fields"), dict) else {}
    for match in re.finditer(r"\b([a-zA-Z_][A-Za-z0-9_]*)\.([a-zA-Z_][A-Za-z0-9_]*)\s*\(", snippet):
        receiver = str(match.group(1) or "").strip()
        method = str(match.group(2) or "").strip()
        symbol = str(fields.get(receiver) or "").strip()
        if not symbol or method in {"println", "info", "warn", "error", "debug"}:
            continue
        if find_source_unit(source_units, symbol):
            return {"symbol": symbol, "method": method}
    return None


def summarize_call_graph(
    *,
    method_call_chain: List[Dict[str, Any]],
    mapped_code_scope: Dict[str, Any],
    code_windows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    layers = [f"{item.get('symbol')}#{item.get('method')}" for item in method_call_chain if item.get("symbol") and item.get("method")]
    discovered_layers: List[str] = []
    for window in code_windows:
        excerpt = str(window.get("excerpt") or "")
        symbol_match = re.search(r"\b(?:class|interface)\s+([A-Z][A-Za-z0-9_]*)\b", excerpt)
        symbol = str(symbol_match.group(1) or "").strip() if symbol_match else ""
        if not symbol:
            continue
        for method_match in re.finditer(
            r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:[\w<>\[\],?]+\s+)+([a-zA-Z_][A-Za-z0-9_]*)\s*\(",
            excerpt,
        ):
            method = str(method_match.group(1) or "").strip()
            if method in {"if", "for", "while", "switch", "catch", "return", "new"}:
                continue
            discovered_layers.append(f"{symbol}#{method}")
    files = [str(item.get("file") or "") for item in method_call_chain if str(item.get("file") or "")]
    dependency_services = list(mapped_code_scope.get("dependency_services") or [])[:10]
    return {
        "entry_method": layers[0] if layers else "",
        "call_path": list(dict.fromkeys([*layers, *discovered_layers]))[:8],
        "call_depth": len(layers),
        "files": list(dict.fromkeys(files))[:8],
        "dependency_services": dependency_services,
    }


def summarize_sql_bindings(*, code_windows: List[Dict[str, Any]], database_tables: List[str]) -> Dict[str, Any]:
    sql_matches: List[str] = []
    tables = [str(item or "").strip() for item in database_tables if str(item or "").strip()]
    for window in code_windows:
        excerpt = str(window.get("excerpt") or "")
        for line in excerpt.splitlines():
            lowered = line.lower()
            if any(keyword in lowered for keyword in ("select ", "update ", "insert ", "delete ", "@query", "<select", "<update")):
                sql_matches.append(line.strip()[:240])
    matched_tables = [table for table in tables if any(table.lower() in item.lower() for item in sql_matches)]
    return {
        "matched_tables": list(dict.fromkeys(matched_tables))[:8],
        "sql_evidence": list(dict.fromkeys(sql_matches))[:6],
    }


def summarize_downstream_rpc(*, code_windows: List[Dict[str, Any]], dependency_services: List[str]) -> Dict[str, Any]:
    rpc_evidence: List[str] = []
    for window in code_windows:
        excerpt = str(window.get("excerpt") or "")
        for line in excerpt.splitlines():
            lowered = line.lower()
            if any(keyword in lowered for keyword in ("feign", "resttemplate", "webclient", "httpclient", "@client", "grpc", "rpc")):
                rpc_evidence.append(line.strip()[:240])
    matched_services = [service for service in dependency_services if any(service.lower() in item.lower() for item in rpc_evidence)]
    return {
        "dependency_services": list(dict.fromkeys(matched_services or dependency_services))[:8],
        "rpc_evidence": list(dict.fromkeys(rpc_evidence))[:6],
    }


def detect_resource_risk_points(*, code_windows: List[Dict[str, Any]]) -> List[str]:
    risk_points: List[str] = []
    patterns = {
        "事务边界可能过长": ("@transactional", "transactiontemplate"),
        "重试可能放大故障": ("retry", "backoff"),
        "连接池/数据库资源竞争": ("hikari", "datasource", "getconnection"),
        "同步下游调用可能阻塞": ("resttemplate", "webclient", "feign", "grpc"),
    }
    for window in code_windows:
        excerpt = str(window.get("excerpt") or "").lower()
        for label, keywords in patterns.items():
            if any(keyword in excerpt for keyword in keywords):
                risk_points.append(label)
    return list(dict.fromkeys(risk_points))[:6]


def summarize_transaction_boundaries(*, code_windows: List[Dict[str, Any]], method_call_chain: List[Dict[str, Any]]) -> Dict[str, Any]:
    boundary_hints: List[str] = []
    for window in code_windows:
        excerpt = str(window.get("excerpt") or "")
        if "@Transactional" in excerpt:
            boundary_hints.append(f"{window.get('file')}: @Transactional")
        if "TransactionTemplate" in excerpt:
            boundary_hints.append(f"{window.get('file')}: TransactionTemplate")
    chain_path = [f"{item.get('symbol')}#{item.get('method')}" for item in method_call_chain[:6]]
    return {
        "boundary_hints": list(dict.fromkeys(boundary_hints))[:6],
        "chain_path": chain_path,
    }
