"""Coverage and convergence scoring contracts for complex incidents."""

from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.messages import AgentEvidence


def _card(agent_name: str, *, evidence_status: str = "ok", confidence: float = 0.8) -> AgentEvidence:
    return AgentEvidence(
        agent_name=agent_name,
        phase="analysis",
        summary=f"{agent_name} summary",
        conclusion=f"{agent_name} conclusion",
        evidence_chain=[],
        confidence=confidence,
        raw_output={"evidence_status": evidence_status},
    )


def test_coverage_scoring_includes_weighted_domain_change_runbook_signals():
    coverage = LangGraphRuntimeOrchestrator._count_key_evidence_coverage(
        [
            _card("LogAgent"),
            _card("CodeAgent"),
            _card("DomainAgent"),
            _card("ChangeAgent"),
            _card("RunbookAgent"),
        ]
    )

    assert coverage["ok"] == 2
    assert coverage["weighted_score"] > 0.5
    assert coverage["corroboration_count"] >= 3
    assert "DomainAgent" in coverage["corroboration_agents"]
