"""Tool context router contract tests."""

from app.services.tool_context.router import decide_tool_invocation, resolve_context_builder_name


def test_resolve_context_builder_name_keeps_agent_to_builder_mapping():
    assert resolve_context_builder_name("CodeAgent") == "_build_code_context"
    assert resolve_context_builder_name("RunbookAgent") == "_build_runbook_context"
    assert resolve_context_builder_name("JudgeAgent") == "_build_rule_suggestion_context"
    assert resolve_context_builder_name("UnknownAgent") is None


def test_decide_tool_invocation_prefers_explicit_boolean_then_text_rules():
    explicit = decide_tool_invocation(
        agent_name="LogAgent",
        assigned_command={"task": "只做现有信息分析", "use_tool": False},
    )
    assert explicit["allow_tool"] is False
    assert explicit["decision_source"] == "explicit_boolean"

    positive = decide_tool_invocation(
        agent_name="CodeAgent",
        assigned_command={"task": "请搜索仓库并检索代码调用链"},
    )
    assert positive["allow_tool"] is True
    assert positive["decision_source"] == "command_text_positive"

    missing = decide_tool_invocation(agent_name="CodeAgent", assigned_command=None)
    assert missing["allow_tool"] is False
    assert missing["decision_source"] == "no_command"
