"""Simple benchmark scoring utilities."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


def _tokenize(text: str) -> List[str]:
    """执行分词相关逻辑，并为当前模块提供可复用的处理能力。"""
    parts = re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", str(text or "").lower())
    return [part for part in parts if part]


def keyword_overlap_score(expected: str, actual: str) -> float:
    """执行keywordoverlap评分相关逻辑，并为当前模块提供可复用的处理能力。"""
    e = set(_tokenize(expected))
    a = set(_tokenize(actual))
    if not e:
        return 0.0
    hit = len(e.intersection(a))
    return max(0.0, min(1.0, hit / max(1, len(e))))


def _claim_graph_items(payload: Any, key: str) -> List[Any]:
    """安全读取 claim_graph 子项，缺失时返回空列表。"""
    if not isinstance(payload, dict):
        return []
    value = payload.get(key)
    if isinstance(value, list):
        return list(value)
    return []


def _extract_claim_texts(items: List[Any], *, fields: List[str]) -> List[str]:
    """从 claim_graph 子项中抽取用于关键词匹配的文本。"""
    texts: List[str] = []
    for item in list(items or []):
        if isinstance(item, dict):
            for field in fields:
                text = str(item.get(field) or "").strip()
                if text:
                    texts.append(text)
        else:
            text = str(item or "").strip()
            if text:
                texts.append(text)
    return texts


def _match_keywords(expectations: List[str], actuals: List[str]) -> float:
    """按关键词重叠统计 expectations 的命中率。"""
    expected = [str(item or "").strip() for item in list(expectations or []) if str(item or "").strip()]
    actual = [str(item or "").strip() for item in list(actuals or []) if str(item or "").strip()]
    if not expected:
        return 0.5
    if not actual:
        return 0.0
    hits = 0
    for item in expected:
        if any(keyword_overlap_score(item, candidate) >= 0.4 for candidate in actual):
            hits += 1
    return round(max(0.0, min(1.0, hits / max(1, len(expected)))), 3)


def _claim_graph_support_score(claim_graph: Dict[str, Any], must_include: List[str]) -> float:
    """根据 supports 和 must_include 计算支持证据得分。"""
    supports = _extract_claim_texts(
        _claim_graph_items(claim_graph, "supports"),
        fields=["summary", "description"],
    )
    if must_include:
        return _match_keywords(must_include, supports)
    if len(supports) >= 3:
        return 1.0
    if len(supports) == 2:
        return 0.75
    if len(supports) == 1:
        return 0.5
    return 0.0


def _claim_graph_exclusion_score(claim_graph: Dict[str, Any], must_exclude: List[str]) -> float:
    """根据 eliminated_alternatives 和 must_exclude 计算排除项得分。"""
    eliminated = _extract_claim_texts(
        _claim_graph_items(claim_graph, "eliminated_alternatives"),
        fields=["summary", "description"],
    )
    if must_exclude:
        return _match_keywords(must_exclude, eliminated)
    return 0.5 if not eliminated else 1.0


def _claim_graph_missing_check_score(
    claim_graph: Dict[str, Any],
    *,
    expected_causal_chain: List[str],
    must_include: List[str],
) -> float:
    """根据 missing_checks 判断系统是否保留了应有的不确定性与验证动作。"""
    missing_checks = _extract_claim_texts(
        _claim_graph_items(claim_graph, "missing_checks"),
        fields=["summary", "description"],
    )
    if expected_causal_chain or must_include:
        return 1.0 if missing_checks else 0.0
    return 0.5 if not missing_checks else 1.0


def evaluate_case(
    *,
    expected_root_cause: str,
    predicted_root_cause: str,
    predicted_candidates: List[str] | None = None,
    claim_graph: Dict[str, Any] | None = None,
    expected_causal_chain: List[str] | None = None,
    must_include: List[str] | None = None,
    must_exclude: List[str] | None = None,
    confidence: float,
    duration_ms: float,
    status: str,
) -> Dict[str, Any]:
    """执行evaluate案例相关逻辑，并为当前模块提供可复用的处理能力。"""
    overlap = keyword_overlap_score(expected_root_cause, predicted_root_cause)
    is_top1 = overlap >= 0.4
    candidate_hits = 0
    for cand in list(predicted_candidates or [])[:5]:
        if keyword_overlap_score(expected_root_cause, str(cand or "")) >= 0.4:
            candidate_hits += 1
            break
    support_score = _claim_graph_support_score(dict(claim_graph or {}), list(must_include or []))
    exclusion_score = _claim_graph_exclusion_score(dict(claim_graph or {}), list(must_exclude or []))
    missing_check_score = _claim_graph_missing_check_score(
        dict(claim_graph or {}),
        expected_causal_chain=list(expected_causal_chain or []),
        must_include=list(must_include or []),
    )
    claim_graph_quality_score = round(
        max(0.0, min(1.0, 0.5 * support_score + 0.3 * exclusion_score + 0.2 * missing_check_score)),
        3,
    )
    return {
        "status": status,
        "duration_ms": round(float(duration_ms or 0.0), 2),
        "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
        "overlap_score": round(overlap, 3),
        "top1_hit": bool(is_top1),
        "top3_hit": bool(is_top1 or candidate_hits > 0),
        "claim_graph_support_score": support_score,
        "claim_graph_exclusion_score": exclusion_score,
        "claim_graph_missing_check_score": missing_check_score,
        "claim_graph_quality_score": claim_graph_quality_score,
    }


def aggregate_cases(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """执行aggregatecases相关逻辑，并为当前模块提供可复用的处理能力。"""
    items = list(rows)
    if not items:
        return {
            "cases": 0,
            "top1_rate": 0.0,
            "top3_rate": 0.0,
            "avg_overlap_score": 0.0,
            "avg_duration_ms": 0.0,
            "avg_first_evidence_latency_ms": 0.0,
            "p95_first_evidence_latency_ms": 0.0,
            "failure_rate": 0.0,
            "timeout_rate": 0.0,
            "empty_conclusion_rate": 0.0,
            "cross_source_evidence_rate": 0.0,
            "avg_claim_graph_quality_score": 0.0,
            "claim_graph_support_rate": 0.0,
            "claim_graph_exclusion_rate": 0.0,
            "claim_graph_missing_check_rate": 0.0,
            "empty_conclusion_by_scenario": {},
        }
    cases = len(items)
    top1_hits = sum(1 for row in items if bool(row.get("top1_hit")))
    top3_hits = sum(1 for row in items if bool(row.get("top3_hit")))
    avg_overlap = sum(float(row.get("overlap_score") or 0.0) for row in items) / cases
    avg_duration = sum(float(row.get("duration_ms") or 0.0) for row in items) / cases
    first_evidence_latencies = [float(row.get("first_evidence_latency_ms") or 0.0) for row in items if float(row.get("first_evidence_latency_ms") or 0.0) > 0]
    avg_first_evidence_latency = (
        sum(first_evidence_latencies) / len(first_evidence_latencies)
        if first_evidence_latencies
        else 0.0
    )
    failures = sum(1 for row in items if str(row.get("status") or "") != "ok")
    timeouts = sum(1 for row in items if "timeout" in str(row.get("status") or "").lower())
    cross_source_hits = sum(1 for row in items if int(row.get("evidence_source_count") or 0) >= 2)
    avg_claim_graph_quality = sum(float(row.get("claim_graph_quality_score") or 0.0) for row in items) / cases
    support_hits = sum(1 for row in items if float(row.get("claim_graph_support_score") or 0.0) >= 0.6)
    exclusion_hits = sum(1 for row in items if float(row.get("claim_graph_exclusion_score") or 0.0) >= 0.6)
    missing_check_hits = sum(1 for row in items if float(row.get("claim_graph_missing_check_score") or 0.0) >= 0.6)
    empties = sum(
        1
        for row in items
        if not str(row.get("predicted_root_cause") or "").strip()
        or str(row.get("predicted_root_cause") or "").strip() in {"unknown", "需要进一步分析"}
    )
    empty_by_scenario: Dict[str, Dict[str, Any]] = {}
    for row in items:
        scenario = str(row.get("scenario") or "unknown")
        bucket = empty_by_scenario.setdefault(scenario, {"cases": 0, "empty": 0})
        bucket["cases"] += 1
        predicted = str(row.get("predicted_root_cause") or "").strip()
        if not predicted or predicted in {"unknown", "需要进一步分析"}:
            bucket["empty"] += 1
    empty_ratio = {
        key: round(float(value.get("empty", 0)) / max(1, int(value.get("cases", 0))), 3)
        for key, value in empty_by_scenario.items()
    }
    return {
        "cases": cases,
        "top1_rate": round(top1_hits / cases, 3),
        "top3_rate": round(top3_hits / cases, 3),
        "avg_overlap_score": round(avg_overlap, 3),
        "avg_duration_ms": round(avg_duration, 2),
        "avg_first_evidence_latency_ms": round(avg_first_evidence_latency, 2),
        "p95_first_evidence_latency_ms": round(_percentile(first_evidence_latencies, 95), 2),
        "failure_rate": round(failures / cases, 3),
        "timeout_rate": round(timeouts / cases, 3),
        "cross_source_evidence_rate": round(cross_source_hits / cases, 3),
        "avg_claim_graph_quality_score": round(avg_claim_graph_quality, 3),
        "claim_graph_support_rate": round(support_hits / cases, 3),
        "claim_graph_exclusion_rate": round(exclusion_hits / cases, 3),
        "claim_graph_missing_check_rate": round(missing_check_hits / cases, 3),
        "empty_conclusion_rate": round(empties / cases, 3),
        "empty_conclusion_by_scenario": empty_ratio,
    }


def _percentile(values: List[float], percentile: int) -> float:
    """执行分位数相关逻辑，并为当前模块提供可复用的处理能力。"""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = (max(0, min(percentile, 100)) / 100) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    if low == high:
        return float(sorted_values[low])
    weight = rank - low
    return float(sorted_values[low] * (1 - weight) + sorted_values[high] * weight)
