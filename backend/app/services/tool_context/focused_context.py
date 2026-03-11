"""Focused-context routing helpers."""

from __future__ import annotations

from typing import Optional


FOCUSED_CONTEXT_BUILDERS = {
    "CodeAgent": "_build_code_focused_context",
    "LogAgent": "_build_log_focused_context",
    "DomainAgent": "_build_domain_focused_context",
    "DatabaseAgent": "_build_database_focused_context",
    "MetricsAgent": "_build_metrics_focused_context",
    "ChangeAgent": "_build_change_focused_context",
    "RunbookAgent": "_build_runbook_focused_context",
    "ProblemAnalysisAgent": "_build_cross_agent_focused_context",
    "CriticAgent": "_build_cross_agent_focused_context",
    "RebuttalAgent": "_build_cross_agent_focused_context",
    "JudgeAgent": "_build_cross_agent_focused_context",
    "VerificationAgent": "_build_cross_agent_focused_context",
    "RuleSuggestionAgent": "_build_cross_agent_focused_context",
}


def resolve_focused_context_builder_name(agent_name: str) -> Optional[str]:
    """Return focused-context builder name for the given agent."""
    return FOCUSED_CONTEXT_BUILDERS.get(str(agent_name or "").strip())
