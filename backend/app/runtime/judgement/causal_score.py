"""Causal scoring helpers for judge outputs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def _source_diversity(evidence: Iterable[Dict[str, Any]]) -> float:
    """执行来源diversity相关逻辑，并为当前模块提供可复用的处理能力。"""
    sources = {str(item.get("source") or "").strip() for item in evidence if str(item.get("source") or "").strip()}
    if not sources:
        return 0.0
    return min(1.0, len(sources) / 3.0)


def _strength_score(evidence: Iterable[Dict[str, Any]]) -> float:
    """执行strength评分相关逻辑，并为当前模块提供可复用的处理能力。"""
    mapping = {"strong": 1.0, "medium": 0.6, "weak": 0.3}
    values: List[float] = []
    for item in evidence:
        values.append(mapping.get(str(item.get("strength") or "medium"), 0.6))
    if not values:
        return 0.0
    return sum(values) / len(values)


def causal_score(
    *,
    root_cause: str,
    evidence: List[Dict[str, Any]],
    confidence: float,
) -> Dict[str, float]:
    """Split relevance vs causality score for final judgment."""

    relevance = max(0.0, min(1.0, float(confidence or 0.0)))
    diversity = _source_diversity(evidence)
    strength = _strength_score(evidence)
    has_root = 1.0 if str(root_cause or "").strip() and str(root_cause).strip() != "Unknown" else 0.0
    causality = max(0.0, min(1.0, 0.45 * strength + 0.35 * diversity + 0.2 * has_root))
    return {
        "relevance_score": round(relevance, 3),
        "causality_score": round(causality, 3),
    }


def has_cross_source_evidence(evidence: List[Dict[str, Any]]) -> bool:
    """执行hascross来源evidence相关逻辑，并为当前模块提供可复用的处理能力。"""
    normalized = {str(item.get("source") or "").strip().lower() for item in evidence if str(item.get("source") or "").strip()}
    # Require at least one log-like source and one code/domain/metrics-like source.
    has_log = any(token in src for src in normalized for token in ("log", "trace", "runtime"))
    has_other = any(token in src for src in normalized for token in ("code", "domain", "metrics", "asset", "git"))
    if has_log and has_other:
        return True
    return len(normalized) >= 2

