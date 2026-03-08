"""test评测评分相关测试。"""

from app.benchmark.scoring import aggregate_cases


def test_aggregate_cases_includes_first_evidence_metrics():
    """验证aggregatecases包含first证据metrics。"""
    
    rows = [
        {
            "top1_hit": True,
            "top3_hit": True,
            "overlap_score": 0.8,
            "duration_ms": 1000,
            "status": "ok",
            "evidence_source_count": 2,
            "predicted_root_cause": "db lock",
            "scenario": "order",
            "first_evidence_latency_ms": 3200,
        },
        {
            "top1_hit": False,
            "top3_hit": True,
            "overlap_score": 0.4,
            "duration_ms": 2000,
            "status": "timeout",
            "evidence_source_count": 1,
            "predicted_root_cause": "需要进一步分析",
            "scenario": "order",
            "first_evidence_latency_ms": 9200,
        },
    ]
    summary = aggregate_cases(rows)
    assert "avg_first_evidence_latency_ms" in summary
    assert "p95_first_evidence_latency_ms" in summary
    assert summary["p95_first_evidence_latency_ms"] >= summary["avg_first_evidence_latency_ms"]
