"""Focused-context router contract tests."""

from app.services.tool_context.focused_context import resolve_focused_context_builder_name


def test_resolve_focused_context_builder_name_keeps_agent_mapping():
    assert resolve_focused_context_builder_name("CodeAgent") == "_build_code_focused_context"
    assert resolve_focused_context_builder_name("ProblemAnalysisAgent") == "_build_cross_agent_focused_context"
    assert resolve_focused_context_builder_name("RuleSuggestionAgent") == "_build_cross_agent_focused_context"
    assert resolve_focused_context_builder_name("UnknownAgent") is None
