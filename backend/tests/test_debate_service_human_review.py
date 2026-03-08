"""test辩论服务人工审核相关测试。"""

import pytest

from app.models.debate import DebatePhase, DebateSession, DebateStatus
from app.repositories.debate_repository import InMemoryDebateRepository
from app.services.debate_service import DebateService, HumanReviewRequired


def _build_waiting_review_session(*, session_id: str, review_status: str = "pending") -> DebateSession:
    """为测试场景提供buildwaiting审核session辅助逻辑。"""
    
    return DebateSession(
        id=session_id,
        incident_id="inc_human_review",
        status=DebateStatus.WAITING,
        current_phase=DebatePhase.JUDGMENT,
        context={
            "trace_id": "deb_trace_review",
            "human_review": {
                "status": review_status,
                "reason": "需要人工确认根因结论",
                "payload": {"root_cause": "db lock"},
                "resume_from_step": "report_generation",
            },
            "pending_review_checkpoint": {
                "debate_result": {
                    "root_cause": "db lock",
                    "confidence": 0.82,
                    "debate_history": [],
                },
                "assets": {"runtime_assets": [], "dev_assets": [], "design_assets": []},
            },
            "event_log": [],
        },
    )


@pytest.mark.asyncio
async def test_execute_debate_raises_human_review_required_when_review_pending():
    """验证execute辩论抛出人工审核required当审核pending。"""
    
    repository = InMemoryDebateRepository()
    service = DebateService(repository=repository)
    session = _build_waiting_review_session(session_id="deb_review_pending")
    await repository.save_session(session)

    with pytest.raises(HumanReviewRequired) as exc_info:
        await service.execute_debate(session.id)

    assert exc_info.value.session_id == session.id
    assert exc_info.value.reason == "需要人工确认根因结论"


@pytest.mark.asyncio
async def test_approve_human_review_updates_review_status_only():
    """验证approve人工审核updates审核statusonly。"""
    
    repository = InMemoryDebateRepository()
    service = DebateService(repository=repository)
    session = _build_waiting_review_session(session_id="deb_review_approve")
    await repository.save_session(session)

    approved = await service.approve_human_review(session.id, approver="alice", comment="looks good")

    assert approved is True
    latest = await repository.get_session(session.id)
    assert latest is not None
    assert latest.status == DebateStatus.WAITING
    assert latest.context["human_review"]["status"] == "approved"
    assert latest.context["human_review"]["approver"] == "alice"
    assert latest.context["pending_review_checkpoint"]["debate_result"]["root_cause"] == "db lock"


@pytest.mark.asyncio
async def test_reject_human_review_marks_session_failed_and_clears_checkpoint():
    """验证reject人工审核标记sessionfailedandclearscheckpoint。"""
    
    repository = InMemoryDebateRepository()
    service = DebateService(repository=repository)
    session = _build_waiting_review_session(session_id="deb_review_reject")
    await repository.save_session(session)

    rejected = await service.reject_human_review(session.id, approver="bob", reason="evidence insufficient")

    assert rejected is True
    latest = await repository.get_session(session.id)
    assert latest is not None
    assert latest.status == DebateStatus.FAILED
    assert latest.context["human_review"]["status"] == "rejected"
    assert latest.context["human_review"]["approver"] == "bob"
    assert latest.context.get("pending_review_checkpoint") is None
    assert latest.context["last_error"] == "evidence insufficient"
