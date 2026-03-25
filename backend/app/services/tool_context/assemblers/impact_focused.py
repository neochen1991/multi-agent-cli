"""Impact-analysis-focused context assembler."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_FUNCTION_HINTS = (
    ("下单", ("下单", "创建订单", "订单创建", "create order", "/orders")),
    ("支付", ("支付", "支付确认", "payment", "/payments")),
    ("库存扣减", ("库存", "扣减库存", "inventory")),
    ("用户登录", ("登录", "signin", "login")),
)


def _guess_functions(texts: List[str], feature: str) -> List[str]:
    picks: List[str] = []
    if feature:
        picks.append(feature)
    merged = " ".join(texts).lower()
    for name, keywords in _FUNCTION_HINTS:
        if any(keyword.lower() in merged for keyword in keywords):
            picks.append(name)
    return list(dict.fromkeys([item[:120] for item in picks if item]))[:6]


def _normalize_endpoint(raw: str) -> Dict[str, str]:
    text = str(raw or "").strip()
    if not text:
        return {"method": "", "path": ""}
    match = re.match(r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(.+)$", text, re.IGNORECASE)
    if match:
        return {
            "method": match.group(1).upper()[:16],
            "path": match.group(2).strip()[:240],
        }
    return {"method": "", "path": text[:240]}


def build_impact_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    # 中文注释：第一版不依赖新的外部工具，只用 incident、责任田映射和 investigation leads
    # 先组织一份足够稳定的 blast radius 上下文，给 ImpactAnalysisAgent 做结构化推断。
    mapping = compact_context.get("interface_mapping") if isinstance(compact_context.get("interface_mapping"), dict) else {}
    endpoint = ((mapping.get("endpoint") or mapping.get("matched_endpoint") or {}) if isinstance(mapping, dict) else {})
    leads = service._extract_investigation_leads(compact_context, incident_context, assigned_command)  # noqa: SLF001
    tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
    if not isinstance(tool_data, dict):
        tool_data = {}

    service_name = str(
        endpoint.get("service")
        or service._primary_service_name(compact_context, incident_context, assigned_command)  # noqa: SLF001
        or ""
    )[:160]
    feature = str(mapping.get("feature") or leads.get("feature") or "")[:120]
    description = str(incident_context.get("description") or compact_context.get("incident_summary", {}).get("description") or "")[:500]
    title = str(compact_context.get("incident_summary", {}).get("title") or incident_context.get("title") or "")[:240]
    focus_text = str((assigned_command or {}).get("focus") or "")[:240]
    signal_texts = [
        title,
        description,
        focus_text,
        " ".join([str(item or "") for item in list(leads.get("error_keywords") or [])[:10]]),
    ]

    functions = _guess_functions(signal_texts, feature)
    raw_endpoints = []
    if endpoint:
        method = str(endpoint.get("method") or "").strip()
        path = str(endpoint.get("path") or "").strip()
        if method or path:
            raw_endpoints.append(f"{method} {path}".strip())
    raw_endpoints.extend([str(item or "").strip() for item in list(leads.get("api_endpoints") or [])[:8]])
    normalized_interfaces: List[Dict[str, Any]] = []
    for raw in raw_endpoints:
        row = _normalize_endpoint(raw)
        if not row["path"]:
            continue
        normalized_interfaces.append(
            {
                "endpoint": row["path"],
                "method": row["method"],
                "service": service_name,
                "error_signal": ",".join(list(leads.get("error_keywords") or [])[:3]),
                "related_function": functions[0] if functions else feature,
            }
        )
    normalized_interfaces = normalized_interfaces[:8]

    unknowns: List[str] = []
    if not normalized_interfaces:
        unknowns.append("缺少明确接口入口，当前仅能给业务功能级影响判断")
    if not any(str(item or "").strip() for item in list(leads.get("monitor_items") or [])[:4]):
        unknowns.append("缺少可直接量化用户影响的监控指标，用户规模可能只能估算")

    severity = str(compact_context.get("incident_summary", {}).get("severity") or incident_context.get("severity") or "medium").strip().lower()
    user_scope = {
        "measured_users": tool_data.get("measured_users"),
        "estimated_users": tool_data.get("estimated_users"),
        "affected_ratio": str(tool_data.get("affected_ratio") or "")[:60],
        "estimation_basis": str(tool_data.get("estimation_basis") or "基于故障窗口、接口入口和责任田服务范围估算")[:200],
        "confidence": float(tool_data.get("confidence") or (0.75 if tool_data.get("measured_users") else 0.58)),
    }

    affected_functions = [
        {
            "name": item,
            "severity": severity if severity in {"critical", "high", "medium", "low"} else "medium",
            "affected_interfaces": [
                interface["endpoint"]
                for interface in normalized_interfaces
                if str(interface.get("related_function") or "") == item
            ][:6],
            "evidence_basis": [
                f"责任田特性映射：{feature}" if feature else "",
                f"告警/日志关键词：{','.join(list(leads.get('error_keywords') or [])[:3])}" if list(leads.get("error_keywords") or []) else "",
            ],
            "user_impact": dict(user_scope),
        }
        for item in functions[:6]
    ]
    for row in affected_functions:
        row["evidence_basis"] = [text for text in row["evidence_basis"] if text][:4]

    return {
        "impact_problem_frame": {
            "title": title,
            "description": description,
            "service": service_name,
            "owner_team": str(mapping.get("owner_team") or leads.get("owner_team") or "")[:120],
            "owner": str(mapping.get("owner") or leads.get("owner") or "")[:120],
            "domain": str(mapping.get("domain") or leads.get("domain") or "")[:120],
            "aggregate": str(mapping.get("aggregate") or leads.get("aggregate") or "")[:120],
        },
        "affected_functions": affected_functions,
        "affected_interfaces": normalized_interfaces,
        "affected_services": [item for item in list(dict.fromkeys([service_name, *list(leads.get("dependency_services") or [])[:4]])) if item][:6],
        "affected_user_scope": user_scope,
        "unknowns": unknowns[:6],
    }
