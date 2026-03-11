"""Per-agent local state contracts for runtime prompts and snapshots."""

from __future__ import annotations

from app.runtime.langgraph.state import structured_state_snapshot


def test_agent_local_state_persists_private_hypotheses_without_leaking_to_shared_context():
    snapshot = structured_state_snapshot(
        {
            "agent_local_state": {
                "CodeAgent": {
                    "private_hypotheses": ["transaction scope too wide"],
                    "verified_evidence_ids": ["evd_code_1"],
                    "missing_checks": ["confirm connection release path"],
                }
            }
        }
    )

    assert snapshot["output_state"]["agent_local_state"]["CodeAgent"]["private_hypotheses"] == [
        "transaction scope too wide"
    ]
    assert "private_hypotheses" not in snapshot.get("context_summary", {})
