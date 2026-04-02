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
    allowed_analysis_agents: Tuple[str, ...]
    parallel_analysis_agents: Tuple[str, ...]
    max_parallel_agents: int
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

    # 中文注释：阶段 1 只把“固定专家池”降级成“允许名单 + 并发预算”。
    # 运行时仍保留 available_analysis_agents 字段给现有 Prompt/图执行复用，
    # 但后续语义会由“必须参与的专家”逐步收缩为“LLM 可选专家集合”。
    all_allowed_agents = (
        "LogAgent",
        "DomainAgent",
        "CodeAgent",
        "DatabaseAgent",
        "MetricsAgent",
        "ImpactAnalysisAgent",
        "ChangeAgent",
        "RunbookAgent",
        "RuleSuggestionAgent",
    )
    default_allowed_agents = all_allowed_agents
    max_parallel_agents = 4

    if phase_mode in {"economy", "failfast"} or execution_mode == "quick":
        # 中文注释：quick 明确是弱模型/低并发保护档。
        # 与 standard 使用同一批可选专家，但进一步压低单轮 fan-out，降低超时与排队风险。
        max_parallel_agents = 3
        max_discussion_steps = 4
        enable_critique = False
        enable_collaboration = False
        require_verification_plan = False
    elif analysis_depth_mode == "deep":
        max_parallel_agents = 6
        max_discussion_steps = 12
        enable_critique = bool(debate_enable_critique)
        enable_collaboration = bool(debate_enable_collaboration)
        require_verification_plan = True
    else:
        max_parallel_agents = 5
        max_discussion_steps = 8
        enable_critique = bool(debate_enable_critique)
        enable_collaboration = bool(debate_enable_collaboration)
        require_verification_plan = True

    deployment_profile_name = ""
    if isinstance(deployment_profile, dict) and deployment_profile.get("name"):
        deployment_profile_name = str(deployment_profile.get("name") or "").strip().lower()
        default_allowed_agents = tuple(
            str(name or "").strip()
            for name in list(deployment_profile.get("allowed_agents") or deployment_profile.get("analysis_agents") or [])
            if str(name or "").strip()
        ) or default_allowed_agents
        try:
            profile_max_parallel = int(deployment_profile.get("max_parallel_agents") or 0)
        except (TypeError, ValueError):
            profile_max_parallel = 0
        if profile_max_parallel > 0:
            max_parallel_agents = profile_max_parallel
        enable_collaboration = bool(deployment_profile.get("collaboration_enabled") or False)
        enable_critique = bool(deployment_profile.get("critique_enabled") or False)
        require_verification_plan = bool(deployment_profile.get("require_verification_plan") or False)

    return RuntimePolicy(
        execution_mode=execution_mode,
        analysis_depth_mode=analysis_depth_mode,
        phase_mode=phase_mode or "standard",
        deployment_profile_name=deployment_profile_name,
        allowed_analysis_agents=tuple(default_allowed_agents),
        parallel_analysis_agents=tuple(default_allowed_agents),
        max_parallel_agents=int(max_parallel_agents),
        max_discussion_steps=int(max_discussion_steps),
        enable_collaboration=bool(enable_collaboration),
        enable_critique=bool(enable_critique),
        require_verification_plan=bool(require_verification_plan),
    )
