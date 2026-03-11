"""Judge / Review boundary helper 测试。"""

from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.langgraph.services.review_boundary import ReviewBoundary


def test_judgment_boundary_can_normalize_judge_output_and_payload() -> None:
    """Judge 边界 helper 应能独立完成输出恢复和最终载荷归一化。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    payload = orchestrator._judgment_boundary.normalize_agent_output(
        "JudgeAgent",
        '{"root_cause":{"summary":"数据库连接池耗尽","category":"db_pool","confidence":0.82},"evidence_chain":["连接获取超时30s"],"confidence":0.82}',
    )
    normalized = orchestrator._judgment_boundary.normalize_final_payload(payload)

    assert normalized["final_judgment"]["root_cause"]["summary"] == "数据库连接池耗尽"
    assert isinstance(normalized["final_judgment"]["evidence_chain"], list)
    assert isinstance(normalized["final_judgment"]["claim_graph"], dict)


def test_review_boundary_shapes_pending_review_state_and_payload() -> None:
    """Review 边界 helper 应统一 session/context 与 final_payload 的审核结构。"""

    boundary = ReviewBoundary()
    review_state = boundary.build_review_state(
        reason="需要值班负责人确认",
        payload={"top_risk": "误回滚"},
        resume_from_step="report_generation",
    )
    final_payload = boundary.attach_review_to_payload({"confidence": 0.61}, review_state)

    assert review_state["status"] == "pending"
    assert review_state["resume_from_step"] == "report_generation"
    assert final_payload["awaiting_human_review"] is True
    assert final_payload["human_review"]["payload"]["top_risk"] == "误回滚"
