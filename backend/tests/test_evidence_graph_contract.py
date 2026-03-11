"""最小证据图合同测试。"""

from datetime import UTC, datetime

from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator, DebateTurn
from app.runtime.messages import AgentEvidence
from app.models.debate import DebateSession, DebateStatus
from app.services.debate_service import DebateService
from app.services.report_generation_service import ReportGenerationService


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    """构造最小 orchestrator，复用 runtime 的最终裁决组装逻辑。"""
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


def test_final_payload_claim_graph_contract_keeps_legacy_evidence_chain() -> None:
    """final_payload 应同时保留 legacy evidence_chain 和新的 claim_graph。"""

    orchestrator = _orchestrator()
    now = datetime.now(UTC)
    judge_output = {
        "final_judgment": {
            "root_cause": {
                "summary": "事务边界覆盖了远程促销校验，导致长事务放大数据库锁等待。",
                "category": "transaction_scope_too_wide",
                "confidence": 0.74,
            },
            "evidence_chain": [
                {"type": "code", "description": "promotionClient.checkQuota 被移入 @Transactional 方法", "source": "CodeAgent", "strength": "strong"},
                {"type": "log", "description": "HikariPool request timed out after 3000ms", "source": "LogAgent", "strength": "strong"},
                {"type": "database", "description": "数据库不是原发根因，只是被长事务放大", "source": "DatabaseAgent", "strength": "strong"},
            ],
            "risk_assessment": {"risk_level": "high", "risk_factors": []},
        },
        "decision_rationale": {
            "reasoning": "数据库不是原发根因，需继续验证回滚后是否恢复。",
            "key_factors": ["待验证回滚后 RT 是否恢复"],
        },
        "confidence": 0.74,
    }
    orchestrator.turns = [
        DebateTurn(
            round_number=1,
            phase="judgment",
            agent_name="JudgeAgent",
            agent_role="技术委员会主席",
            model={"name": "glm-5"},
            input_message="",
            output_content=judge_output,
            confidence=0.74,
            started_at=now,
            completed_at=now,
        )
    ]
    history_cards = [
        AgentEvidence(
            agent_name="CriticAgent",
            phase="critique",
            summary="仍需确认是否只是流量突增",
            conclusion="如果回滚后仍异常，需要排除纯流量峰值场景。",
            evidence_chain=[],
            confidence=0.51,
            raw_output={},
        )
    ]

    payload = orchestrator._judgment_boundary.build_final_payload(
        history_cards=history_cards,
        consensus_reached=False,
        executed_rounds=1,
    )

    final_judgment = payload["final_judgment"]
    assert isinstance(final_judgment["evidence_chain"], list)
    assert len(final_judgment["evidence_chain"]) == 3
    claim_graph = final_judgment["claim_graph"]
    assert claim_graph["primary_claim"]["category"] == "transaction_scope_too_wide"
    assert isinstance(claim_graph["supports"], list)
    assert isinstance(claim_graph["contradicts"], list)
    assert isinstance(claim_graph["missing_checks"], list)
    assert isinstance(claim_graph["eliminated_alternatives"], list)


def test_result_and_report_preserve_claim_graph_contract() -> None:
    """结果层和报告层都应透传 claim_graph，而不是只保留 evidence_chain。"""

    session = DebateSession(
        id="deb_evidence_graph",
        incident_id="inc_evidence_graph",
        status=DebateStatus.COMPLETED,
        context={},
    )
    flow_result = {
        "confidence": 0.72,
        "final_judgment": {
            "root_cause": {
                "summary": "RiskService 重试缺少总超时预算。",
                "category": "upstream_timeout_budget_missing",
                "confidence": 0.72,
            },
            "evidence_chain": [
                {"type": "log", "description": "重试时间线累计约 30.4s", "source": "LogAgent", "strength": "strong"},
            ],
            "claim_graph": {
                "primary_claim": {
                    "summary": "RiskService 重试缺少总超时预算。",
                    "category": "upstream_timeout_budget_missing",
                    "confidence": 0.72,
                },
                "supports": [{"type": "log", "summary": "重试时间线累计约 30.4s", "source": "LogAgent", "strength": "strong"}],
                "contradicts": [],
                "missing_checks": ["验证熔断是否生效"],
                "eliminated_alternatives": ["数据库不是原发根因"],
            },
        },
        "action_items": [],
        "responsible_team": {"team": "payment-team", "owner": "neo"},
    }

    debate_result = DebateService()._build_result(session, flow_result, report={})
    assert debate_result.claim_graph["primary_claim"]["category"] == "upstream_timeout_budget_missing"

    report_payload = ReportGenerationService()._format_as_json(
        ReportGenerationService()._get_default_report_structure(),
        {"id": "inc_evidence_graph", "title": "payment timeout"},
        flow_result,
        assets={},
    )
    assert '"claim_graph"' in report_payload
