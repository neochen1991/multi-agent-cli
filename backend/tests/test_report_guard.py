from datetime import datetime

from app.models.debate import DebateResult, EvidenceItem
from app.services.report_service import ReportService


def _result(root_cause: str, confidence: float, evidence: list[EvidenceItem]) -> DebateResult:
    return DebateResult(
        session_id="deb_test",
        incident_id="inc_test",
        root_cause=root_cause,
        root_cause_category="runtime",
        confidence=confidence,
        evidence_chain=evidence,
        action_items=[],
        dissenting_opinions=[],
        debate_history=[],
        created_at=datetime.utcnow(),
    )


def test_report_guard_rejects_placeholder_conclusion():
    value = _result(
        "需要进一步分析",
        0.8,
        [
            EvidenceItem(type="log", description="log-1", source="log", location=None, strength="medium"),
            EvidenceItem(type="code", description="code-1", source="code", location=None, strength="medium"),
        ],
    )
    assert not ReportService._has_effective_debate_result(value)


def test_report_guard_rejects_zero_confidence_or_empty_evidence():
    low = _result(
        "数据库连接池耗尽",
        0.0,
        [
            EvidenceItem(type="log", description="log-1", source="log", location=None, strength="medium"),
            EvidenceItem(type="code", description="code-1", source="code", location=None, strength="medium"),
        ],
    )
    assert not ReportService._has_effective_debate_result(low)

    no_evidence = _result("数据库连接池耗尽", 0.7, [])
    assert not ReportService._has_effective_debate_result(no_evidence)


def test_report_guard_accepts_effective_result():
    ok = _result(
        "数据库连接池耗尽",
        0.7,
        [
            EvidenceItem(type="log", description="hikari timeout", source="log", location=None, strength="strong"),
            EvidenceItem(type="code", description="OrderAppService transaction too long", source="code", location=None, strength="medium"),
        ],
    )
    assert ReportService._has_effective_debate_result(ok)


def test_report_guard_rejects_single_source_evidence():
    only_log = _result(
        "数据库连接池耗尽",
        0.8,
        [
            EvidenceItem(type="log", description="hikari timeout", source="log", location=None, strength="strong"),
            EvidenceItem(type="log", description="db active 100/100", source="log", location=None, strength="strong"),
        ],
    )
    assert not ReportService._has_effective_debate_result(only_log)
