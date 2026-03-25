"""test评测评分相关测试。"""

from pathlib import Path

from app.benchmark.fixtures import load_fixtures
from app.benchmark.scoring import aggregate_cases, evaluate_case


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


def test_evaluate_case_scores_claim_graph_quality():
    """claim_graph richer scoring 应识别支持证据、排除项和待验证项。"""

    score = evaluate_case(
        expected_root_cause="事务边界覆盖远程调用导致长事务",
        predicted_root_cause="事务边界覆盖远程调用导致长事务",
        predicted_candidates=["数据库锁等待是放大器"],
        claim_graph={
            "supports": [
                {"summary": "promotionClient.checkQuota 被移入 @Transactional"},
                {"summary": "HikariPool timeout after 3000ms"},
            ],
            "eliminated_alternatives": ["数据库不是原发根因，只是被长事务放大"],
            "missing_checks": ["验证回滚后 promotion latency 是否恢复"],
        },
        expected_causal_chain=["长事务", "连接池耗尽", "数据库锁等待放大"],
        must_include=["@Transactional", "HikariPool timeout"],
        must_exclude=["数据库不是原发根因"],
        confidence=0.72,
        duration_ms=1200,
        status="ok",
    )

    assert score["claim_graph_support_score"] >= 0.5
    assert score["claim_graph_exclusion_score"] == 1.0
    assert score["claim_graph_missing_check_score"] == 1.0
    assert score["claim_graph_quality_score"] >= 0.7


def test_aggregate_cases_includes_claim_graph_metrics():
    """聚合统计应输出 claim_graph 质量指标。"""

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
            "claim_graph_support_score": 1.0,
            "claim_graph_exclusion_score": 1.0,
            "claim_graph_missing_check_score": 1.0,
            "claim_graph_quality_score": 1.0,
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
            "claim_graph_support_score": 0.0,
            "claim_graph_exclusion_score": 0.5,
            "claim_graph_missing_check_score": 0.0,
            "claim_graph_quality_score": 0.15,
        },
    ]

    summary = aggregate_cases(rows)

    assert summary["avg_claim_graph_quality_score"] > 0.5
    assert "claim_graph_support_rate" in summary
    assert "claim_graph_exclusion_rate" in summary
    assert "claim_graph_missing_check_rate" in summary


def test_load_fixtures_reads_richer_claim_graph_scoring_fields():
    """fixture loader 应读取 richer scoring 所需的扩展字段。"""

    fixtures = load_fixtures(limit=30)
    target = next(item for item in fixtures if item.fixture_id == "fixture_inc_21")

    assert any("数据库热点锁竞争" in item for item in target.must_exclude)
    assert len(target.must_include) >= 2
    assert len(target.expected_causal_chain) >= 2


def test_load_fixtures_reads_expected_impact_fields():
    """fixture loader 应读取 impact-analysis richer 期望字段。"""

    fixtures = load_fixtures(limit=40)
    target = next(item for item in fixtures if item.fixture_id == "fixture_inc_23")

    assert target.expected_impact["affected_functions"] == ["订单创建"]
    assert "/api/v1/orders" in target.expected_impact["affected_interfaces"]
    assert target.expected_impact["require_user_scope"] is True
