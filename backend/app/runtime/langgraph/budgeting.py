"""Budget and timeout rules for runtime execution."""

from __future__ import annotations

from typing import Any, Iterable, List


def is_fast_execution_mode(execution_mode_name: str) -> bool:
    # quick 明确面向弱模型/低并发场景；background 是执行方式，不再等同于快模式策略。
    return str(execution_mode_name or "").strip().lower() == "quick"


def has_expert_turns(turns: Iterable[Any]) -> bool:
    for turn in list(turns or []):
        agent_name = str(getattr(turn, "agent_name", "") or "").strip()
        if not agent_name:
            return True
        if agent_name != "ProblemAnalysisAgent":
            return True
    return False


def is_fast_first_round(*, execution_mode_name: str, require_verification_plan: bool, turns: Iterable[Any]) -> bool:
    return is_fast_execution_mode(execution_mode_name) and not require_verification_plan and not list(turns or [])


def is_fast_analysis_opening(*, execution_mode_name: str, require_verification_plan: bool, turns: Iterable[Any]) -> bool:
    return is_fast_execution_mode(execution_mode_name) and not require_verification_plan and not has_expert_turns(turns)


def agent_max_tokens(
    *,
    agent_name: str,
    debate_judge_max_tokens: int,
    debate_review_max_tokens: int,
    debate_analysis_max_tokens: int,
    deployment_profile_name: str,
    analysis_depth_mode_name: str,
    require_verification_plan: bool,
    turns: Iterable[Any],
    execution_mode_name: str,
) -> int:
    depth_mode = str(analysis_depth_mode_name or "").strip().lower()
    if agent_name == "JudgeAgent":
        configured = int(debate_judge_max_tokens)
        if depth_mode == "deep":
            return max(1100, min(configured, 1800))
        return max(900, min(configured, 1600))
    if agent_name in {"CriticAgent", "RebuttalAgent"}:
        configured = int(debate_review_max_tokens)
        if depth_mode == "deep":
            return max(760, min(configured, 1300))
        return max(560, min(configured, 1100))
    if agent_name == "ProblemAnalysisAgent":
        configured = int(debate_analysis_max_tokens)
        if depth_mode == "deep":
            return max(820, min(configured, 1400))
        if deployment_profile_name in {"investigation_full", "production_governed"} and not list(turns or []):
            return max(280, min(configured, 360))
        if not require_verification_plan and not list(turns or []):
            return max(360, min(configured, 480))
        return max(620, min(configured, 1100))
    configured = int(debate_analysis_max_tokens)
    if depth_mode == "deep":
        return max(760, min(configured, 1300))
    if is_fast_analysis_opening(
        execution_mode_name=execution_mode_name,
        require_verification_plan=require_verification_plan,
        turns=turns,
    ):
        return max(360, min(configured, 480))
    return max(560, min(configured, 1100))


def agent_timeout_plan(
    *,
    agent_name: str,
    llm_judge_timeout: int,
    llm_judge_retry_timeout: int,
    llm_analysis_timeout: int,
    llm_review_timeout: int,
    analysis_depth_mode_name: str,
    require_verification_plan: bool,
    execution_mode_name: str,
    turns: Iterable[Any],
) -> List[float]:
    depth_mode = str(analysis_depth_mode_name or "").strip().lower()
    if agent_name == "JudgeAgent":
        if depth_mode == "deep":
            first_timeout = float(max(50, int(llm_judge_timeout)))
            retry_timeout = float(max(first_timeout + 15, int(llm_judge_retry_timeout) + 10))
            return [first_timeout, retry_timeout]
        if not require_verification_plan:
            first_timeout = float(max(55, int(llm_judge_timeout)))
            retry_timeout = float(max(first_timeout + 15, int(llm_judge_retry_timeout) + 15))
            return [first_timeout, retry_timeout]
        first_timeout = float(max(30, int(llm_judge_timeout)))
        retry_timeout = float(max(first_timeout + 10, int(llm_judge_retry_timeout)))
        return [first_timeout, retry_timeout]
    if agent_name == "ProblemAnalysisAgent":
        if depth_mode == "deep":
            first_timeout = float(max(35, int(llm_analysis_timeout)))
            retry_timeout = float(max(first_timeout + 10, min(int(llm_analysis_timeout) + 25, 90)))
            return [first_timeout, retry_timeout]
        if not require_verification_plan:
            return [float(max(60, int(llm_analysis_timeout)))]
        first_timeout = float(max(20, int(llm_analysis_timeout)))
        retry_timeout = float(max(first_timeout + 10, min(int(llm_analysis_timeout) + 20, 75)))
        return [first_timeout, retry_timeout]
    if agent_name in {"CriticAgent", "RebuttalAgent"}:
        if depth_mode == "deep":
            return [float(max(40, int(llm_review_timeout)))]
        return [float(max(30, int(llm_review_timeout)))]
    if depth_mode == "deep":
        return [float(max(40, int(llm_analysis_timeout)))]
    if is_fast_analysis_opening(
        execution_mode_name=execution_mode_name,
        require_verification_plan=require_verification_plan,
        turns=turns,
    ):
        return [float(max(60, int(llm_analysis_timeout)))]
    return [float(max(20, int(llm_analysis_timeout)))]


def agent_http_timeout(
    *,
    agent_name: str,
    llm_judge_retry_timeout: int,
    llm_review_timeout: int,
    llm_analysis_timeout: int,
    analysis_depth_mode_name: str,
    require_verification_plan: bool,
    execution_mode_name: str,
    turns: Iterable[Any],
) -> int:
    depth_mode = str(analysis_depth_mode_name or "").strip().lower()
    if agent_name == "JudgeAgent":
        if depth_mode == "deep":
            return max(65, min(int(llm_judge_retry_timeout) + 20, 160))
        if not require_verification_plan:
            return max(80, min(int(llm_judge_retry_timeout) + 25, 150))
        return max(45, min(int(llm_judge_retry_timeout) + 10, 120))
    if agent_name in {"CriticAgent", "RebuttalAgent"}:
        if depth_mode == "deep":
            return max(50, min(int(llm_review_timeout) + 15, 120))
        return max(35, min(int(llm_review_timeout) + 10, 100))
    if depth_mode == "deep":
        return max(50, min(int(llm_analysis_timeout) + 20, 130))
    if is_fast_analysis_opening(
        execution_mode_name=execution_mode_name,
        require_verification_plan=require_verification_plan,
        turns=turns,
    ):
        return max(70, min(int(llm_analysis_timeout) + 20, 120))
    return max(30, min(int(llm_analysis_timeout) + 10, 100))


def agent_queue_timeout(
    *,
    agent_name: str,
    llm_queue_timeout: int,
    llm_analysis_queue_timeout: int,
    llm_metrics_queue_timeout: int,
    llm_judge_queue_timeout: int,
    deployment_profile_name: str,
    analysis_depth_mode_name: str,
    execution_mode_name: str,
    require_verification_plan: bool,
    turns: Iterable[Any],
) -> float:
    depth_mode = str(analysis_depth_mode_name or "").strip().lower()
    base_timeout = float(max(2, int(llm_queue_timeout)))
    analysis_timeout = float(max(base_timeout, int(llm_analysis_queue_timeout)))
    metrics_timeout = float(max(analysis_timeout, int(llm_metrics_queue_timeout)))
    judge_timeout = float(max(analysis_timeout, int(llm_judge_queue_timeout)))
    if agent_name == "JudgeAgent":
        if depth_mode == "deep":
            return float(max(judge_timeout, 95.0))
        return judge_timeout
    if agent_name == "ProblemAnalysisAgent":
        if depth_mode == "deep":
            return float(max(min(judge_timeout - 5.0, judge_timeout), analysis_timeout + 15.0, 80.0))
        if deployment_profile_name in {"investigation_full", "production_governed"} and not list(turns or []):
            return float(max(min(judge_timeout - 10.0, judge_timeout), analysis_timeout + 10.0, 70.0))
        return float(max(min(judge_timeout - 15.0, judge_timeout), analysis_timeout + 5.0, 60.0))
    if agent_name == "MetricsAgent":
        if depth_mode == "deep":
            return float(max(metrics_timeout, 95.0))
        if deployment_profile_name in {"investigation_full", "production_governed"}:
            return float(max(metrics_timeout, 90.0))
        return float(max(metrics_timeout, 75.0))
    if depth_mode == "deep" and agent_name in {"LogAgent", "CodeAgent", "DatabaseAgent", "ChangeAgent", "DomainAgent", "RunbookAgent", "RuleSuggestionAgent"}:
        return float(max(analysis_timeout, 75.0))
    if is_fast_execution_mode(execution_mode_name) and agent_name in {"LogAgent", "CodeAgent", "DatabaseAgent", "ChangeAgent", "DomainAgent"}:
        return float(max(analysis_timeout, 60.0))
    if deployment_profile_name in {"investigation_full", "production_governed"} and agent_name in {"LogAgent", "CodeAgent", "DatabaseAgent", "ChangeAgent", "DomainAgent"}:
        return float(max(analysis_timeout, 60.0))
    if agent_name in {"CriticAgent", "RebuttalAgent", "VerificationAgent"}:
        return float(max(base_timeout + 10.0, 50.0))
    return base_timeout
