"""终态收口服务测试。"""

from app.runtime.langgraph.services.finalization_service import FinalizationService
from app.runtime.langgraph.services.review_boundary import ReviewBoundary
from app.runtime.langgraph.services.judgment_boundary import JudgmentBoundary


def test_finalization_service_builds_payload_when_missing() -> None:
    """当 state 未显式写入 final_payload 时，服务应调用兜底构造器。"""

    calls = []

    def _build_final_payload(**kwargs):
        calls.append(dict(kwargs))
        return {
            "confidence": 0.74,
            "final_judgment": {"root_cause": {"summary": "连接池耗尽", "confidence": 0.74}},
        }

    service = FinalizationService(
        build_final_payload=_build_final_payload,
        review_boundary=ReviewBoundary(),
        normalize_final_payload=JudgmentBoundary.normalize_final_payload,
    )
    decision = service.resolve(
        state={},
        history_cards=[],
        consensus_reached=True,
        executed_rounds=2,
    )

    assert len(calls) == 1
    assert decision.awaiting_human_review is False
    assert decision.final_payload["confidence"] == 0.74
    assert decision.runtime_event["type"] == "runtime_debate_completed"


def test_finalization_service_attaches_human_review_metadata() -> None:
    """等待人工审核时，应把 review 载荷统一封装进 final_payload。"""

    service = FinalizationService(
        build_final_payload=lambda **kwargs: {
            "confidence": 0.61,
            "final_judgment": {"root_cause": {"summary": "证据不足", "confidence": 0.61}},
        },
        review_boundary=ReviewBoundary(),
        normalize_final_payload=JudgmentBoundary.normalize_final_payload,
    )

    decision = service.resolve(
        state={
            "awaiting_human_review": True,
            "human_review_reason": "需要值班负责人确认",
            "human_review_payload": {"top_risk": "误回滚"},
            "resume_from_step": "report_generation",
        },
        history_cards=[],
        consensus_reached=False,
        executed_rounds=1,
    )

    assert decision.awaiting_human_review is True
    assert decision.final_payload["awaiting_human_review"] is True
    assert decision.final_payload["human_review"]["reason"] == "需要值班负责人确认"
    assert decision.final_payload["human_review"]["payload"]["top_risk"] == "误回滚"
    assert decision.runtime_event["type"] == "runtime_human_review_requested"
    assert decision.runtime_event["resume_from_step"] == "report_generation"
