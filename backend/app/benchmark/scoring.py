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
    confidence: float,
    duration_ms: float,
    status: str,
) -> Dict[str, Any]:
    overlap = keyword_overlap_score(expected_root_cause, predicted_root_cause)
    is_top1 = overlap >= 0.4
    return {
        "status": status,
        "duration_ms": round(float(duration_ms or 0.0), 2),
        "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
        "overlap_score": round(overlap, 3),
        "top1_hit": bool(is_top1),
    }


def aggregate_cases(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(rows)
    if not items:
        return {
            "cases": 0,
            "top1_rate": 0.0,
            "avg_overlap_score": 0.0,
            "avg_duration_ms": 0.0,
            "failure_rate": 0.0,
            "timeout_rate": 0.0,
            "empty_conclusion_rate": 0.0,
        }
    cases = len(items)
    top1_hits = sum(1 for row in items if bool(row.get("top1_hit")))
    avg_overlap = sum(float(row.get("overlap_score") or 0.0) for row in items) / cases
    avg_duration = sum(float(row.get("duration_ms") or 0.0) for row in items) / cases
    failures = sum(1 for row in items if str(row.get("status") or "") != "ok")
    timeouts = sum(1 for row in items if "timeout" in str(row.get("status") or "").lower())
    empties = sum(
        1
        for row in items
        if not str(row.get("predicted_root_cause") or "").strip()
        or str(row.get("predicted_root_cause") or "").strip() in {"unknown", "需要进一步分析"}
    )
    return {
        "cases": cases,
        "top1_rate": round(top1_hits / cases, 3),
        "avg_overlap_score": round(avg_overlap, 3),
        "avg_duration_ms": round(avg_duration, 2),
        "failure_rate": round(failures / cases, 3),
        "timeout_rate": round(timeouts / cases, 3),
        "empty_conclusion_rate": round(empties / cases, 3),
    }

