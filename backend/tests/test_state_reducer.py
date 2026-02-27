"""
Unit tests for State Reducers.
"""

import pytest
from app.runtime.langgraph.state import (
    merge_agent_outputs,
    extend_evidence_chain,
    extend_history_cards,
    merge_claims,
    merge_context,
    take_latest,
    increment_counter,
    create_initial_state,
    get_state_summary,
    DebateExecState,
    structured_state_snapshot,
    sync_structured_state,
)
from app.runtime.messages import AgentEvidence


class TestMergeAgentOutputs:
    """Tests for merge_agent_outputs reducer."""

    def test_merge_empty_left(self):
        """Should return right when left is None."""
        result = merge_agent_outputs(None, {"LogAgent": {"confidence": 0.8}})
        assert result == {"LogAgent": {"confidence": 0.8}}

    def test_merge_empty_right(self):
        """Should return left when right is None."""
        result = merge_agent_outputs({"LogAgent": {"confidence": 0.8}}, None)
        assert result == {"LogAgent": {"confidence": 0.8}}

    def test_merge_combines_dicts(self):
        """Should merge two dicts."""
        left = {"LogAgent": {"confidence": 0.8}}
        right = {"CodeAgent": {"confidence": 0.7}}

        result = merge_agent_outputs(left, right)

        assert result == {
            "LogAgent": {"confidence": 0.8},
            "CodeAgent": {"confidence": 0.7},
        }

    def test_merge_overwrites_same_key(self):
        """Should overwrite left value with right value for same key."""
        left = {"LogAgent": {"confidence": 0.8}}
        right = {"LogAgent": {"confidence": 0.9}}

        result = merge_agent_outputs(left, right)

        assert result == {"LogAgent": {"confidence": 0.9}}


class TestExtendEvidenceChain:
    """Tests for extend_evidence_chain reducer."""

    def test_extend_empty_left(self):
        """Should return right when left is None."""
        result = extend_evidence_chain(None, [{"type": "log"}])
        assert result == [{"type": "log"}]

    def test_extend_empty_right(self):
        """Should return left when right is None."""
        result = extend_evidence_chain([{"type": "log"}], None)
        assert result == [{"type": "log"}]

    def test_extend_appends_lists(self):
        """Should append right to left."""
        left = [{"type": "log"}]
        right = [{"type": "code"}]

        result = extend_evidence_chain(left, right)

        assert result == [{"type": "log"}, {"type": "code"}]

    def test_extend_preserves_order(self):
        """Should preserve order of items."""
        left = [{"id": 1}, {"id": 2}]
        right = [{"id": 3}, {"id": 4}]

        result = extend_evidence_chain(left, right)

        assert result == [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]


class TestExtendHistoryCards:
    """Tests for extend_history_cards reducer."""

    def create_card(self, agent_name: str) -> AgentEvidence:
        return AgentEvidence(
            agent_name=agent_name,
            phase="analysis",
            summary="Test",
            conclusion="Test",
            confidence=0.8,
        )

    def test_extend_empty_left(self):
        """Should return right when left is None."""
        card = self.create_card("LogAgent")
        result = extend_history_cards(None, [card])
        assert result == [card]

    def test_extend_appends_cards(self):
        """Should append new cards to existing."""
        left = [self.create_card("LogAgent")]
        right = [self.create_card("CodeAgent")]

        result = extend_history_cards(left, right)

        assert len(result) == 2
        assert result[0].agent_name == "LogAgent"
        assert result[1].agent_name == "CodeAgent"


class TestMergeClaims:
    """Tests for merge_claims reducer."""

    def test_merge_claims_appends(self):
        """Should append claims."""
        left = [{"agent": "LogAgent", "claim": "Error in log"}]
        right = [{"agent": "CodeAgent", "claim": "Bug in code"}]

        result = merge_claims(left, right)

        assert len(result) == 2


class TestMergeContext:
    """Tests for merge_context reducer."""

    def test_merge_context_shallow(self):
        """Should merge top-level keys."""
        left = {"log_content": "error log", "trace_id": "123"}
        right = {"code_file": "main.py"}

        result = merge_context(left, right)

        assert result["log_content"] == "error log"
        assert result["trace_id"] == "123"
        assert result["code_file"] == "main.py"

    def test_merge_context_deep(self):
        """Should deep merge nested dicts."""
        left = {"parsed_data": {"errors": ["Error1"], "count": 1}}
        right = {"parsed_data": {"warnings": ["Warn1"], "count": 2}}

        result = merge_context(left, right)

        assert result["parsed_data"]["errors"] == ["Error1"]
        assert result["parsed_data"]["warnings"] == ["Warn1"]
        assert result["parsed_data"]["count"] == 2  # Right overwrites

    def test_merge_context_empty(self):
        """Should handle None values."""
        result = merge_context(None, {"key": "value"})
        assert result == {"key": "value"}

        result = merge_context({"key": "value"}, None)
        assert result == {"key": "value"}


class TestTakeLatest:
    """Tests for take_latest reducer."""

    def test_takes_right_when_present(self):
        """Should return right when right is not None."""
        result = take_latest("old_value", "new_value")
        assert result == "new_value"

    def test_takes_left_when_right_is_none(self):
        """Should return left when right is None."""
        result = take_latest("old_value", None)
        assert result == "old_value"

    def test_handles_none_left(self):
        """Should handle None left."""
        result = take_latest(None, "new_value")
        assert result == "new_value"


class TestIncrementCounter:
    """Tests for increment_counter reducer."""

    def test_increments_positive(self):
        """Should add values."""
        result = increment_counter(5, 3)
        assert result == 8

    def test_handles_none_left(self):
        """Should treat None left as 0."""
        result = increment_counter(None, 5)
        assert result == 5

    def test_handles_none_right(self):
        """Should treat None right as 0."""
        result = increment_counter(5, None)
        assert result == 5

    def test_handles_both_none(self):
        """Should return 0 when both are None."""
        result = increment_counter(None, None)
        assert result == 0


class TestCreateInitialState:
    """Tests for create_initial_state."""

    def test_creates_state_with_context(self):
        """Should create state with provided context."""
        context = {"log_content": "error log", "trace_id": "123"}
        state = create_initial_state(context)

        assert state["context"] == context
        assert state["current_round"] == 1
        assert state["executed_rounds"] == 0
        assert state["consensus_reached"] is False
        assert state["discussion_step_count"] == 0

    def test_creates_state_with_custom_max_steps(self):
        """Should create state with custom max discussion steps."""
        context = {}
        state = create_initial_state(context, max_discussion_steps=30)

        assert state["max_discussion_steps"] == 30

    def test_creates_empty_collections(self):
        """Should initialize empty collections."""
        context = {}
        state = create_initial_state(context)

        assert state["history_cards"] == []
        assert state["agent_outputs"] == {}
        assert state["evidence_chain"] == []
        assert state["claims"] == []
        assert state["messages"] == []
        assert state["phase_state"]["current_round"] == 1
        assert state["routing_state"]["next_step"] == ""
        assert state["output_state"]["history_cards"] == []


class TestStructuredState:
    """Tests for structured state snapshot helpers."""

    def test_structured_state_snapshot_from_flat_state(self):
        flat = {
            "current_round": 2,
            "executed_rounds": 1,
            "consensus_reached": False,
            "continue_next_round": True,
            "next_step": "speak:LogAgent",
            "agent_commands": {"LogAgent": {"task": "analyze logs"}},
            "discussion_step_count": 3,
            "max_discussion_steps": 12,
            "round_start_turn_index": 1,
            "supervisor_stop_requested": False,
            "supervisor_stop_reason": "",
            "supervisor_notes": [{"reason": "test"}],
            "history_cards": [],
            "agent_outputs": {"LogAgent": {"conclusion": "x"}},
            "evidence_chain": [{"type": "log"}],
            "claims": [{"agent_name": "LogAgent"}],
            "open_questions": ["Q1"],
            "final_payload": {"confidence": 0.8},
        }

        snapshot = structured_state_snapshot(flat)

        assert snapshot["phase_state"]["current_round"] == 2
        assert snapshot["routing_state"]["next_step"] == "speak:LogAgent"
        assert snapshot["output_state"]["final_payload"]["confidence"] == 0.8

    def test_sync_structured_state_keeps_flat_and_adds_structured(self):
        update = {
            "current_round": 1,
            "next_step": "",
            "history_cards": [],
            "agent_outputs": {},
            "evidence_chain": [],
            "claims": [],
            "open_questions": [],
            "final_payload": {},
        }

        merged = sync_structured_state(update)

        assert merged["current_round"] == 1
        assert "phase_state" in merged
        assert "routing_state" in merged
        assert "output_state" in merged


class TestGetStateSummary:
    """Tests for get_state_summary."""

    def test_returns_summary(self):
        """Should return summary dict."""
        state = {
            "current_round": 2,
            "discussion_step_count": 5,
            "history_cards": [1, 2, 3],
            "agent_outputs": {"LogAgent": {}},
            "evidence_chain": [1, 2],
            "consensus_reached": False,
            "supervisor_stop_requested": False,
            "next_step": "speak:JudgeAgent",
        }

        summary = get_state_summary(state)

        assert summary["current_round"] == 2
        assert summary["discussion_step_count"] == 5
        assert summary["history_cards_count"] == 3
        assert summary["agent_outputs_count"] == 1
        assert summary["evidence_chain_count"] == 2
        assert summary["consensus_reached"] is False
        assert summary["next_step"] == "speak:JudgeAgent"
