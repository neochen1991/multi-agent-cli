"""Budgeting and timeout rule tests."""

from datetime import datetime

from app.runtime.langgraph.budgeting import (
    agent_http_timeout,
    agent_max_tokens,
    agent_queue_timeout,
    agent_timeout_plan,
    is_fast_analysis_opening,
    is_fast_execution_mode,
    is_fast_first_round,
)
from app.runtime.langgraph.state import DebateTurn


def _turn(agent_name: str) -> DebateTurn:
    return DebateTurn(
        round_number=1,
        phase="analysis",
        agent_name=agent_name,
        agent_role="test",
        model={"provider": "test", "name": "test"},
        input_message="test",
        output_content={"chat_message": "test"},
        confidence=0.6,
        started_at=datetime.utcnow(),
    )


def test_fast_mode_helpers_distinguish_first_round_and_expert_opening():
    turns = []
    assert is_fast_execution_mode("quick") is True
    assert is_fast_first_round(
        execution_mode_name="quick",
        require_verification_plan=False,
        turns=turns,
    ) is True
    assert is_fast_analysis_opening(
        execution_mode_name="quick",
        require_verification_plan=False,
        turns=turns,
    ) is True

    commander_only_turns = [_turn("ProblemAnalysisAgent")]
    assert is_fast_first_round(
        execution_mode_name="quick",
        require_verification_plan=False,
        turns=commander_only_turns,
    ) is False
    assert is_fast_analysis_opening(
        execution_mode_name="quick",
        require_verification_plan=False,
        turns=commander_only_turns,
    ) is True

    expert_turns = [_turn("ProblemAnalysisAgent"), _turn("LogAgent")]
    assert is_fast_analysis_opening(
        execution_mode_name="quick",
        require_verification_plan=False,
        turns=expert_turns,
    ) is False


def test_agent_max_tokens_preserves_fast_mode_and_judge_budgets():
    assert agent_max_tokens(
        agent_name="JudgeAgent",
        debate_judge_max_tokens=1400,
        debate_review_max_tokens=700,
        debate_analysis_max_tokens=800,
        deployment_profile_name="",
        analysis_depth_mode_name="standard",
        require_verification_plan=True,
        turns=[],
        execution_mode_name="standard",
    ) == 1400

    assert agent_max_tokens(
        agent_name="ProblemAnalysisAgent",
        debate_judge_max_tokens=1400,
        debate_review_max_tokens=700,
        debate_analysis_max_tokens=900,
        deployment_profile_name="",
        analysis_depth_mode_name="quick",
        require_verification_plan=False,
        turns=[],
        execution_mode_name="quick",
    ) == 480

    assert agent_max_tokens(
        agent_name="LogAgent",
        debate_judge_max_tokens=1400,
        debate_review_max_tokens=700,
        debate_analysis_max_tokens=900,
        deployment_profile_name="",
        analysis_depth_mode_name="quick",
        require_verification_plan=False,
        turns=[],
        execution_mode_name="quick",
    ) == 480


def test_timeout_rules_preserve_relaxed_fast_mode_budget():
    assert agent_timeout_plan(
        agent_name="ProblemAnalysisAgent",
        llm_judge_timeout=75,
        llm_judge_retry_timeout=60,
        llm_analysis_timeout=55,
        llm_review_timeout=60,
        analysis_depth_mode_name="quick",
        require_verification_plan=False,
        execution_mode_name="quick",
        turns=[],
    ) == [60.0]

    assert agent_http_timeout(
        agent_name="LogAgent",
        llm_judge_retry_timeout=60,
        llm_review_timeout=60,
        llm_analysis_timeout=55,
        analysis_depth_mode_name="quick",
        require_verification_plan=False,
        execution_mode_name="quick",
        turns=[],
    ) == 75

    assert agent_queue_timeout(
        agent_name="MetricsAgent",
        llm_queue_timeout=45,
        llm_analysis_queue_timeout=60,
        llm_metrics_queue_timeout=90,
        llm_judge_queue_timeout=90,
        deployment_profile_name="investigation_full",
        analysis_depth_mode_name="standard",
        execution_mode_name="standard",
        require_verification_plan=True,
        turns=[_turn("ProblemAnalysisAgent")],
    ) == 90.0
