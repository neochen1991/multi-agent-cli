"""Depth-policy tests for runtime strategy and expert budgets."""

from app.runtime.langgraph.runtime_policy import resolve_runtime_policy
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator


def test_deep_mode_expands_runtime_policy_beyond_round_count():
    policy = resolve_runtime_policy(
        {
            "execution_mode": "standard",
            "analysis_depth_mode": "deep",
        },
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )

    assert policy.max_discussion_steps > 8
    assert policy.max_parallel_agents == 6
    assert "ChangeAgent" in policy.allowed_analysis_agents
    assert "RunbookAgent" in policy.allowed_analysis_agents
    assert policy.enable_critique is True
    assert policy.enable_collaboration is True


def test_deep_mode_relaxes_analysis_agent_budget():
    standard = LangGraphRuntimeOrchestrator(
        consensus_threshold=0.75,
        max_rounds=0,
        analysis_depth_mode="standard",
    )
    deep = LangGraphRuntimeOrchestrator(
        consensus_threshold=0.75,
        max_rounds=0,
        analysis_depth_mode="deep",
    )

    standard._configure_runtime_policy({"execution_mode": "standard", "analysis_depth_mode": "standard"})
    deep._configure_runtime_policy({"execution_mode": "standard", "analysis_depth_mode": "deep"})

    assert deep._agent_max_tokens("CodeAgent") > standard._agent_max_tokens("CodeAgent")
    assert deep._agent_timeout_plan("CodeAgent")[0] >= standard._agent_timeout_plan("CodeAgent")[0]
