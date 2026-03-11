"""test状态reducer相关测试。"""

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
    flatten_structured_state_view,
    flatten_structured_overrides,
    StateAccessor,
)
from app.runtime.messages import AgentEvidence


class TestMergeAgentOutputs:
    """归档MergeAgentOutputs相关测试场景。"""

    def test_merge_empty_left(self):
        """验证merge空left。"""
        result = merge_agent_outputs(None, {"LogAgent": {"confidence": 0.8}})
        assert result == {"LogAgent": {"confidence": 0.8}}

    def test_merge_empty_right(self):
        """验证merge空right。"""
        result = merge_agent_outputs({"LogAgent": {"confidence": 0.8}}, None)
        assert result == {"LogAgent": {"confidence": 0.8}}

    def test_merge_combines_dicts(self):
        """验证mergecombinesdicts。"""
        left = {"LogAgent": {"confidence": 0.8}}
        right = {"CodeAgent": {"confidence": 0.7}}

        result = merge_agent_outputs(left, right)

        assert result == {
            "LogAgent": {"confidence": 0.8},
            "CodeAgent": {"confidence": 0.7},
        }

    def test_merge_overwrites_same_key(self):
        """验证mergeoverwrites相同key。"""
        left = {"LogAgent": {"confidence": 0.8}}
        right = {"LogAgent": {"confidence": 0.9}}

        result = merge_agent_outputs(left, right)

        assert result == {"LogAgent": {"confidence": 0.9}}


class TestExtendEvidenceChain:
    """归档ExtendEvidenceChain相关测试场景。"""

    def test_extend_empty_left(self):
        """验证extend空left。"""
        result = extend_evidence_chain(None, [{"type": "log"}])
        assert result == [{"type": "log"}]

    def test_extend_empty_right(self):
        """验证extend空right。"""
        result = extend_evidence_chain([{"type": "log"}], None)
        assert result == [{"type": "log"}]

    def test_extend_appends_lists(self):
        """验证extendappendslists。"""
        left = [{"type": "log"}]
        right = [{"type": "code"}]

        result = extend_evidence_chain(left, right)

        assert result == [{"type": "log"}, {"type": "code"}]

    def test_extend_preserves_order(self):
        """验证extendpreservesorder。"""
        left = [{"id": 1}, {"id": 2}]
        right = [{"id": 3}, {"id": 4}]

        result = extend_evidence_chain(left, right)

        assert result == [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]


class TestExtendHistoryCards:
    """归档ExtendHistoryCards相关测试场景。"""

    def create_card(self, agent_name: str) -> AgentEvidence:
        """为测试场景提供创建卡片辅助逻辑。"""
        
        return AgentEvidence(
            agent_name=agent_name,
            phase="analysis",
            summary="Test",
            conclusion="Test",
            confidence=0.8,
        )

    def test_extend_empty_left(self):
        """验证extend空left。"""
        card = self.create_card("LogAgent")
        result = extend_history_cards(None, [card])
        assert result == [card]

    def test_extend_appends_cards(self):
        """验证extendappendscards。"""
        left = [self.create_card("LogAgent")]
        right = [self.create_card("CodeAgent")]

        result = extend_history_cards(left, right)

        assert len(result) == 2
        assert result[0].agent_name == "LogAgent"
        assert result[1].agent_name == "CodeAgent"


class TestMergeClaims:
    """归档MergeClaims相关测试场景。"""

    def test_merge_claims_appends(self):
        """验证mergeclaimsappends。"""
        left = [{"agent": "LogAgent", "claim": "Error in log"}]
        right = [{"agent": "CodeAgent", "claim": "Bug in code"}]

        result = merge_claims(left, right)

        assert len(result) == 2


class TestMergeContext:
    """归档MergeContext相关测试场景。"""

    def test_merge_context_shallow(self):
        """验证merge上下文shallow。"""
        left = {"log_content": "error log", "trace_id": "123"}
        right = {"code_file": "main.py"}

        result = merge_context(left, right)

        assert result["log_content"] == "error log"
        assert result["trace_id"] == "123"
        assert result["code_file"] == "main.py"

    def test_merge_context_deep(self):
        """验证merge上下文deep。"""
        left = {"parsed_data": {"errors": ["Error1"], "count": 1}}
        right = {"parsed_data": {"warnings": ["Warn1"], "count": 2}}

        result = merge_context(left, right)

        assert result["parsed_data"]["errors"] == ["Error1"]
        assert result["parsed_data"]["warnings"] == ["Warn1"]
        assert result["parsed_data"]["count"] == 2  # Right overwrites

    def test_merge_context_empty(self):
        """验证merge上下文空。"""
        result = merge_context(None, {"key": "value"})
        assert result == {"key": "value"}

        result = merge_context({"key": "value"}, None)
        assert result == {"key": "value"}


class TestTakeLatest:
    """归档TakeLatest相关测试场景。"""

    def test_takes_right_when_present(self):
        """验证takesright当present。"""
        result = take_latest("old_value", "new_value")
        assert result == "new_value"

    def test_takes_left_when_right_is_none(self):
        """验证takesleft当rightisnone。"""
        result = take_latest("old_value", None)
        assert result == "old_value"

    def test_handles_none_left(self):
        """验证处理noneleft。"""
        result = take_latest(None, "new_value")
        assert result == "new_value"


class TestIncrementCounter:
    """归档IncrementCounter相关测试场景。"""

    def test_increments_positive(self):
        """验证incrementspositive。"""
        result = increment_counter(5, 3)
        assert result == 8

    def test_handles_none_left(self):
        """验证处理noneleft。"""
        result = increment_counter(None, 5)
        assert result == 5

    def test_handles_none_right(self):
        """验证处理noneright。"""
        result = increment_counter(5, None)
        assert result == 5

    def test_handles_both_none(self):
        """验证处理bothnone。"""
        result = increment_counter(None, None)
        assert result == 0


class TestCreateInitialState:
    """归档CreateInitialState相关测试场景。"""

    def test_creates_state_with_context(self):
        """验证creates状态带上下文。"""
        context = {"log_content": "error log", "trace_id": "123"}
        state = create_initial_state(context)

        assert state["context"] == context
        assert state["current_round"] == 1
        assert state["executed_rounds"] == 0
        assert state["consensus_reached"] is False
        assert state["discussion_step_count"] == 0

    def test_creates_state_with_custom_max_steps(self):
        """验证creates状态带custommaxsteps。"""
        context = {}
        state = create_initial_state(context, max_discussion_steps=30)

        assert state["max_discussion_steps"] == 30

    def test_creates_empty_collections(self):
        """验证creates空collections。"""
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

    def test_creates_state_from_structured_authoritative_seed(self):
        """初始化应由结构化状态统一镜像出兼容 flat 字段。"""

        state = create_initial_state({}, max_discussion_steps=16)

        assert state["phase_state"]["current_round"] == 1
        assert state["routing_state"]["max_discussion_steps"] == 16
        assert state["output_state"]["agent_outputs"] == {}
        flat = flatten_structured_state_view(state)
        assert flat["current_round"] == 1
        assert flat["max_discussion_steps"] == 16
        assert flat["agent_outputs"] == {}


class TestStructuredState:
    """归档StructuredState相关测试场景。"""

    def test_structured_state_snapshot_from_flat_state(self):
        """验证结构化状态快照从flat状态。"""
        
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
        """验证同步结构化状态保留flatandadds结构化。"""
        
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

    def test_structured_state_snapshot_prefers_nested_values(self):
        """验证结构化状态快照prefersnestedvalues。"""
        
        payload = {
            "current_round": 1,
            "next_step": "speak:LogAgent",
            "phase_state": {
                "current_round": 3,
                "executed_rounds": 2,
                "consensus_reached": True,
                "continue_next_round": False,
            },
            "routing_state": {
                "next_step": "finalize",
            },
        }

        snapshot = structured_state_snapshot(payload)

        assert snapshot["phase_state"]["current_round"] == 3
        assert snapshot["routing_state"]["next_step"] == "finalize"

    def test_flatten_structured_state_view_merges_flat_and_nested(self):
        """验证flatten结构化状态viewmergesflatandnested。"""
        
        payload = {
            "current_round": 1,
            "discussion_step_count": 2,
            "phase_state": {"current_round": 4},
            "routing_state": {"discussion_step_count": 7},
        }

        flat = flatten_structured_state_view(payload)

        assert flat["current_round"] == 4
        assert flat["discussion_step_count"] == 7

    def test_flatten_structured_overrides_only_returns_explicit_keys(self):
        """验证flatten结构化overridesonly返回显式keys。"""
        
        overrides = flatten_structured_overrides(
            {
                "routing_state": {"next_step": "judge_agent_node"},
                "output_state": {"agent_outputs": {"JudgeAgent": {"conclusion": "ok"}}},
            }
        )

        assert overrides["next_step"] == "judge_agent_node"
        assert "agent_outputs" in overrides
        assert "current_round" not in overrides


class TestStateAccessor:
    """归档StateAccessor相关测试场景。"""

    def test_build_update_prefers_structured_state_as_authority(self):
        """build_update 应先写结构化状态，再镜像 flat 字段。"""

        state = {
            "phase_state": {"current_round": 1, "consensus_reached": False},
            "routing_state": {"next_step": "analysis_parallel", "discussion_step_count": 0},
            "output_state": {"history_cards": [], "agent_outputs": {}},
        }

        update = StateAccessor.build_update(
            state,
            current_round=3,
            next_step="speak:JudgeAgent",
            discussion_step=2,
            consensus_reached=True,
        )

        assert update["phase_state"]["current_round"] == 3
        assert update["phase_state"]["consensus_reached"] is True
        assert update["routing_state"]["next_step"] == "speak:JudgeAgent"
        assert update["routing_state"]["discussion_step_count"] == 2
        flat = flatten_structured_state_view(update)
        assert flat["current_round"] == 3
        assert flat["next_step"] == "speak:JudgeAgent"
        assert flat["discussion_step_count"] == 2

    def test_setters_mirror_flat_fields_from_structured_source(self):
        """单字段 setter 也应通过结构化状态镜像兼容 flat 字段。"""

        state = {
            "phase_state": {"current_round": 1},
            "routing_state": {"next_step": "", "discussion_step_count": 0},
        }

        next_step_update = StateAccessor.set_next_step(state, "judge_agent_node")
        discussion_update = StateAccessor.set_discussion_step(state, 4)

        assert next_step_update["routing_state"]["next_step"] == "judge_agent_node"
        assert next_step_update["next_step"] == "judge_agent_node"
        assert discussion_update["routing_state"]["discussion_step_count"] == 4
        assert discussion_update["discussion_step_count"] == 4


class TestGetStateSummary:
    """归档GetStateSummary相关测试场景。"""

    def test_returns_summary(self):
        """验证返回摘要。"""
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
