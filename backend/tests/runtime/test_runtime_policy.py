"""Runtime policy selection tests."""

from app.runtime.langgraph.runtime_policy import resolve_runtime_policy


def test_resolve_runtime_policy_for_quick_mode_uses_budget_guardrails():
    policy = resolve_runtime_policy(
        {"execution_mode": "quick"},
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )

    assert policy.execution_mode == "quick"
    assert policy.phase_mode == "standard"
    assert "ImpactAnalysisAgent" in policy.allowed_analysis_agents
    assert "RunbookAgent" in policy.allowed_analysis_agents
    assert policy.parallel_analysis_agents == policy.allowed_analysis_agents
    assert policy.max_parallel_agents == 3
    assert policy.max_discussion_steps == 4
    assert policy.enable_collaboration is False
    assert policy.enable_critique is False
    assert policy.require_verification_plan is False


def test_resolve_runtime_policy_for_standard_mode_uses_full_analysis_policy():
    policy = resolve_runtime_policy(
        {"execution_mode": "standard"},
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )

    assert "MetricsAgent" in policy.allowed_analysis_agents
    assert "ChangeAgent" in policy.allowed_analysis_agents
    assert policy.max_parallel_agents == 5
    assert policy.max_discussion_steps == 8
    assert policy.enable_collaboration is True
    assert policy.enable_critique is True
    assert policy.require_verification_plan is True


def test_resolve_runtime_policy_keeps_same_allowed_agents_for_quick_and_standard():
    """验证 quick 和 standard 共用同一批可选专家，只在预算和治理开关上分化。"""

    quick = resolve_runtime_policy(
        {"execution_mode": "quick"},
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )
    standard = resolve_runtime_policy(
        {"execution_mode": "standard"},
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )

    assert quick.allowed_analysis_agents == standard.allowed_analysis_agents
    assert quick.max_parallel_agents < standard.max_parallel_agents
    assert quick.require_verification_plan is False
    assert standard.require_verification_plan is True


def test_resolve_runtime_policy_for_background_mode_keeps_standard_analysis_shape():
    policy = resolve_runtime_policy(
        {"execution_mode": "background"},
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )

    assert "MetricsAgent" in policy.allowed_analysis_agents
    assert policy.max_parallel_agents == 5
    assert policy.max_discussion_steps == 8
    assert policy.enable_collaboration is True
    assert policy.enable_critique is True
    assert policy.require_verification_plan is True


def test_resolve_runtime_policy_honors_deployment_profile_overrides():
    policy = resolve_runtime_policy(
        {
            "execution_mode": "standard",
            "deployment_profile": {
                "name": "investigation_full",
                "allowed_agents": ["LogAgent", "CodeAgent", "DatabaseAgent", "DomainAgent"],
                "max_parallel_agents": 3,
                "collaboration_enabled": True,
                "critique_enabled": True,
                "require_verification_plan": True,
            },
        },
        debate_enable_critique=False,
        debate_enable_collaboration=False,
    )

    assert policy.deployment_profile_name == "investigation_full"
    assert policy.allowed_analysis_agents == ("LogAgent", "CodeAgent", "DatabaseAgent", "DomainAgent")
    assert policy.max_parallel_agents == 3
    assert policy.enable_collaboration is True
    assert policy.enable_critique is True
    assert policy.require_verification_plan is True
