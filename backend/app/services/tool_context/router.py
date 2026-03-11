"""Routing helpers for agent tool context selection."""

from __future__ import annotations

from typing import Dict, Optional


AGENT_CONTEXT_BUILDERS: Dict[str, str] = {
    "CodeAgent": "_build_code_context",
    "ProblemAnalysisAgent": "_build_rule_suggestion_context",
    "ChangeAgent": "_build_change_context",
    "LogAgent": "_build_log_context",
    "MetricsAgent": "_build_metrics_context",
    "RunbookAgent": "_build_runbook_context",
    "CriticAgent": "_build_metrics_context",
    "RebuttalAgent": "_build_log_context",
    "JudgeAgent": "_build_rule_suggestion_context",
    "VerificationAgent": "_build_metrics_context",
    "RuleSuggestionAgent": "_build_rule_suggestion_context",
    "DomainAgent": "_build_domain_context",
    "DatabaseAgent": "_build_database_context",
}


def resolve_context_builder_name(agent_name: str) -> Optional[str]:
    """Return the builder method name for an agent."""
    return AGENT_CONTEXT_BUILDERS.get(str(agent_name or "").strip())


def decide_tool_invocation(*, agent_name: str, assigned_command: Optional[Dict[str, object]]) -> Dict[str, object]:
    """Decide whether the current agent may invoke tools for this round."""
    command = dict(assigned_command or {})
    text_fields = [
        str(command.get("task") or "").strip(),
        str(command.get("focus") or "").strip(),
        str(command.get("expected_output") or "").strip(),
    ]
    skill_hints = command.get("skill_hints")
    has_skill_hints = isinstance(skill_hints, list) and bool(
        [str(item or "").strip() for item in skill_hints if str(item or "").strip()]
    )
    has_command = bool(any(text_fields)) or ("use_tool" in command) or has_skill_hints
    if not has_command:
        return {
            "agent_name": agent_name,
            "has_command": False,
            "allow_tool": False,
            "reason": "未收到主Agent命令",
            "decision_source": "no_command",
        }

    use_tool_raw = command.get("use_tool")
    if isinstance(use_tool_raw, bool):
        return {
            "agent_name": agent_name,
            "has_command": True,
            "allow_tool": use_tool_raw,
            "reason": "主Agent命令显式指定工具开关",
            "decision_source": "explicit_boolean",
        }

    merged = " ".join(text_fields).lower()
    disable_terms = ("无需工具", "不要调用工具", "禁止调用工具", "仅基于现有信息", "不查日志", "不查代码", "不查责任田")
    if any(term in merged for term in disable_terms):
        return {
            "agent_name": agent_name,
            "has_command": True,
            "allow_tool": False,
            "reason": "主Agent命令要求不调用工具",
            "decision_source": "command_text_negative",
        }

    enable_terms = (
        "读取日志",
        "查询日志",
        "检索代码",
        "搜索仓库",
        "查责任田",
        "excel",
        "csv",
        "git",
        "repo",
        "指标",
        "监控",
        "cpu",
        "线程",
        "连接池",
        "grafana",
        "apm",
        "trace",
        "链路",
        "变更",
        "发布",
        "commit",
        "runbook",
        "案例库",
        "sop",
        "日志云",
        "logcloud",
        "告警平台",
        "alert",
        "数据库",
        "慢sql",
        "top sql",
        "索引",
        "表结构",
        "session",
    )
    if any(term in merged for term in enable_terms):
        return {
            "agent_name": agent_name,
            "has_command": True,
            "allow_tool": True,
            "reason": "主Agent命令要求外部证据检索",
            "decision_source": "command_text_positive",
        }

    return {
        "agent_name": agent_name,
        "has_command": True,
        "allow_tool": True,
        "reason": "收到主Agent命令，按Agent默认工具策略执行",
        "decision_source": "command_default",
    }
