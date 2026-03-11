"""Runtime policy selection for debate execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class RuntimePolicy:
    execution_mode: str
    analysis_depth_mode: str
    phase_mode: str
    deployment_profile_name: str
    parallel_analysis_agents: Tuple[str, ...]
    max_discussion_steps: int
    enable_collaboration: bool
    enable_critique: bool
    require_verification_plan: bool


def resolve_runtime_policy(context: Dict[str, Any], *, debate_enable_critique: bool, debate_enable_collaboration: bool) -> RuntimePolicy:
    """Resolve runtime policy from execution mode, runtime strategy, and deployment profile."""

    execution_mode = str((context or {}).get("execution_mode") or "standard").strip().lower()
    analysis_depth_mode = str((context or {}).get("analysis_depth_mode") or "standard").strip().lower()
    if analysis_depth_mode not in {"quick", "standard", "deep"}:
        analysis_depth_mode = "standard"
    deployment_profile = (context or {}).get("deployment_profile")
    runtime_strategy = (context or {}).get("runtime_strategy")
    phase_mode = ""
    if isinstance(runtime_strategy, dict):
        phase_mode = str(runtime_strategy.get("phase_mode") or "").strip().lower()

    core_agents = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")
    balanced_agents = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent", "MetricsAgent")
    fast_agents = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent", "MetricsAgent", "ChangeAgent")
    deep_agents = (
        "LogAgent",
        "DomainAgent",
        "CodeAgent",
        "DatabaseAgent",
        "MetricsAgent",
        "ChangeAgent",
        "RunbookAgent",
        "RuleSuggestionAgent",
    )

    if phase_mode in {"economy", "failfast"} or execution_mode == "quick":
        selected_agents = core_agents
        max_discussion_steps = 4
        enable_critique = False
        enable_collaboration = False
        require_verification_plan = False
    elif phase_mode == "fast_track" or execution_mode in {"background", "async"}:
        selected_agents = fast_agents
        max_discussion_steps = 10
        enable_critique = False
        enable_collaboration = False
        require_verification_plan = False
    elif analysis_depth_mode == "deep":
        selected_agents = deep_agents
        max_discussion_steps = 12
        enable_critique = bool(debate_enable_critique)
        enable_collaboration = bool(debate_enable_collaboration)
        require_verification_plan = True
    else:
        selected_agents = balanced_agents
        max_discussion_steps = 8
        enable_critique = bool(debate_enable_critique)
        enable_collaboration = bool(debate_enable_collaboration)
        require_verification_plan = True

    deployment_profile_name = ""
    if isinstance(deployment_profile, dict) and deployment_profile.get("name"):
        deployment_profile_name = str(deployment_profile.get("name") or "").strip().lower()
        selected_agents = tuple(
            str(name or "").strip()
            for name in list(deployment_profile.get("analysis_agents") or [])
            if str(name or "").strip()
        ) or selected_agents
        enable_collaboration = bool(deployment_profile.get("collaboration_enabled") or False)
        enable_critique = bool(deployment_profile.get("critique_enabled") or False)
        require_verification_plan = bool(deployment_profile.get("require_verification_plan") or False)

    return RuntimePolicy(
        execution_mode=execution_mode,
        analysis_depth_mode=analysis_depth_mode,
        phase_mode=phase_mode or "standard",
        deployment_profile_name=deployment_profile_name,
        parallel_analysis_agents=tuple(selected_agents),
        max_discussion_steps=int(max_discussion_steps),
        enable_collaboration=bool(enable_collaboration),
        enable_critique=bool(enable_critique),
        require_verification_plan=bool(require_verification_plan),
    )
