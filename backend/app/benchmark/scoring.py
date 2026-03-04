"""Simple benchmark scoring utilities."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


def _tokenize(text: str) -> List[str]:
    parts = re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", str(text or "").lower())
    return [part for part in parts if part]


def keyword_overlap_score(expected: str, actual: str) -> float:
    e = set(_tokenize(expected))
    a = set(_tokenize(actual))
    if not e:
        return 0.0
    hit = len(e.intersection(a))
    return max(0.0, min(1.0, hit / max(1, len(e))))


def evaluate_case(
    *,
    expected_root_cause: str,
    predicted_root_cause: str,
    predicted_candidates: List[str] | None = None,
    confidence: float,
    duration_ms: float,
    status: str,
) -> Dict[str, Any]:
    overlap = keyword_overlap_score(expected_root_cause, predicted_root_cause)
    is_top1 = overlap >= 0.4
    candidate_hits = 0
    for cand in list(predicted_candidates or [])[:5]:
        if keyword_overlap_score(expected_root_cause, str(cand or "")) >= 0.4:
            candidate_hits += 1
            break
    return {
        "status": status,
        "duration_ms": round(float(duration_ms or 0.0), 2),
        "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
        "overlap_score": round(overlap, 3),
        "top1_hit": bool(is_top1),
        "top3_hit": bool(is_top1 or candidate_hits > 0),
    }


def aggregate_cases(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
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
        "empty_conclusion_rate": round(empties / cases, 3),
        "empty_conclusion_by_scenario": empty_ratio,
    }


def _percentile(values: List[float], percentile: int) -> float:
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
