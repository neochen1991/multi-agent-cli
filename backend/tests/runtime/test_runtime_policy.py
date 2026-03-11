"""Runtime policy selection tests."""

from app.runtime.langgraph.runtime_policy import resolve_runtime_policy


def test_resolve_runtime_policy_for_quick_mode_uses_core_agents():
    policy = resolve_runtime_policy(
        {"execution_mode": "quick"},
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )

    assert policy.execution_mode == "quick"
    assert policy.phase_mode == "standard"
    assert policy.parallel_analysis_agents == ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")
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

    assert policy.parallel_analysis_agents == (
        "LogAgent",
        "DomainAgent",
        "CodeAgent",
        "DatabaseAgent",
        "MetricsAgent",
    )
    assert policy.max_discussion_steps == 8
    assert policy.enable_collaboration is True
    assert policy.enable_critique is True
    assert policy.require_verification_plan is True


def test_resolve_runtime_policy_for_background_mode_keeps_standard_analysis_shape():
    policy = resolve_runtime_policy(
        {"execution_mode": "background"},
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )

    assert policy.parallel_analysis_agents == (
        "LogAgent",
        "DomainAgent",
        "CodeAgent",
        "DatabaseAgent",
        "MetricsAgent",
    )
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
                "analysis_agents": ["LogAgent", "CodeAgent", "DatabaseAgent", "DomainAgent"],
                "collaboration_enabled": True,
                "critique_enabled": True,
                "require_verification_plan": True,
            },
        },
        debate_enable_critique=False,
        debate_enable_collaboration=False,
    )

    assert policy.deployment_profile_name == "investigation_full"
    assert policy.parallel_analysis_agents == ("LogAgent", "CodeAgent", "DatabaseAgent", "DomainAgent")
    assert policy.enable_collaboration is True
    assert policy.enable_critique is True
    assert policy.require_verification_plan is True
