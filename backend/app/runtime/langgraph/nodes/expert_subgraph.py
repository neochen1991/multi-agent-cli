"""关键专家多步调查子图辅助逻辑。"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping

from app.runtime.langgraph.state import AgentSpec

KEY_EXPERT_AGENTS = frozenset({"LogAgent", "CodeAgent", "DatabaseAgent", "MetricsAgent"})


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    """把上下文裁剪成适合注入调查备忘录的小体积结构。"""
    if depth >= 3:
        return str(value)[:240]
    if isinstance(value, dict):
        return {
            str(key): _compact_value(item, depth=depth + 1)
            for key, item in list(value.items())[:8]
        }
    if isinstance(value, list):
        return [_compact_value(item, depth=depth + 1) for item in value[:8]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:240]


def _to_json(value: Any) -> str:
    """使用紧凑 JSON，避免中间备忘录把最终 prompt 冲得过大。"""
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


def should_run_expert_subgraph(
    *,
    spec: AgentSpec,
    execution_context: Mapping[str, Any] | None,
    analysis_depth_mode: str,
    fast_execution_mode: bool,
) -> bool:
    """判断当前 Agent 是否应进入多步调查闭环。"""
    if spec.phase != "analysis":
        return False
    if spec.name not in KEY_EXPERT_AGENTS:
        return False
    if fast_execution_mode:
        return False
    context = dict(execution_context or {})
    has_signal = any(
        context.get(key)
        for key in ("focused_context", "tool_context", "agent_local_context")
    )
    if not has_signal:
        return False
    return str(analysis_depth_mode or "standard").strip().lower() in {"standard", "deep"}


def build_investigation_plan_prompt(
    *,
    spec: AgentSpec,
    base_prompt: str,
    execution_context: Mapping[str, Any] | None,
    analysis_depth_mode: str,
) -> str:
    """生成第一步“多步调查计划”提示。"""
    context = dict(execution_context or {})
    memo = {
        "focused_context": _compact_value(context.get("focused_context") or {}),
        "tool_context": _compact_value(context.get("tool_context") or {}),
        "agent_local_context": _compact_value(context.get("agent_local_context") or {}),
    }
    return (
        f"你是 {spec.name}，请先输出多步调查计划，不要直接给最终结论。\n"
        f"分析深度模式: {str(analysis_depth_mode or 'standard').strip().lower()}\n"
        "请只输出一个 JSON 对象，字段建议包含 hypotheses、checks、next_focus、missing_evidence。\n"
        "目标是先把你的调查路径拆清楚，便于后续综合结论。\n\n"
        f"原始任务:\n{base_prompt}\n\n"
        f"调查上下文:\n```json\n{_to_json(memo)}\n```"
    )


def build_reflection_prompt(
    *,
    spec: AgentSpec,
    base_prompt: str,
    investigation_memo: Mapping[str, Any],
) -> str:
    """生成 deep 模式下的反证复核提示。"""
    return (
        f"你是 {spec.name}，请对已有调查计划做反证复核，不要直接给最终结论。\n"
        "请只输出一个 JSON 对象，字段建议包含 contradictions、missing_checks、risk_focus、revised_focus。\n"
        "优先指出哪条假设可能站不住，或还缺哪项验证。\n\n"
        f"原始任务:\n{base_prompt}\n\n"
        f"当前调查计划:\n```json\n{_to_json(_compact_value(dict(investigation_memo or {})))}\n```"
    )


def build_synthesis_prompt(
    *,
    spec: AgentSpec,
    base_prompt: str,
    investigation_memo: Mapping[str, Any],
    reflection_memo: Mapping[str, Any] | None,
) -> str:
    """把中间调查备忘录压回最终结论 prompt。"""
    synthesis_payload: Dict[str, Any] = {
        "investigation_plan": _compact_value(dict(investigation_memo or {})),
    }
    if reflection_memo:
        synthesis_payload["reflection_review"] = _compact_value(dict(reflection_memo or {}))
    return (
        f"{base_prompt}\n\n"
        "补充约束：请基于下面的调查备忘录给出最终结构化结论，不要忽略其中的假设、验证项和反证提醒。\n"
        "最终仍然只能输出业务约定的 JSON 结果。\n\n"
        f"调查备忘录:\n```json\n{_to_json(synthesis_payload)}\n```"
    )


__all__ = [
    "KEY_EXPERT_AGENTS",
    "should_run_expert_subgraph",
    "build_investigation_plan_prompt",
    "build_reflection_prompt",
    "build_synthesis_prompt",
]
