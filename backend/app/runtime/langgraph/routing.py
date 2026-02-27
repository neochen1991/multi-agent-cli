"""Pure routing and guardrail helpers for LangGraph debate runtime."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.runtime.messages import AgentEvidence


def _agent_output_from_state(state: Dict[str, Any], agent_name: str) -> Dict[str, Any]:
    outputs = state.get("agent_outputs")
    if not isinstance(outputs, dict):
        return {}
    payload = outputs.get(str(agent_name or "").strip())
    return payload if isinstance(payload, dict) else {}


def _output_confidence(payload: Dict[str, Any], default: float = 0.0) -> float:
    if not isinstance(payload, dict):
        return float(default or 0.0)
    for key in ("confidence",):
        value = payload.get(key)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass
    final_judgment = payload.get("final_judgment")
    if isinstance(final_judgment, dict):
        root_cause = final_judgment.get("root_cause")
        if isinstance(root_cause, dict):
            try:
                if root_cause.get("confidence") is not None:
                    return float(root_cause.get("confidence"))
            except (TypeError, ValueError):
                pass
    return float(default or 0.0)


def step_for_agent(agent_name: str) -> str:
    return f"speak:{str(agent_name or '').strip()}"


def agent_from_step(step: str) -> str:
    text = str(step or "").strip()
    return text.split(":", 1)[1].strip() if text.startswith("speak:") and ":" in text else ""


def supervisor_step_to_node(next_step: str) -> str:
    step = str(next_step or "").strip()
    if not step:
        return "round_evaluate"
    if step in ("analysis_parallel", "parallel_analysis"):
        return "analysis_parallel_node"
    if step == "analysis_collaboration":
        return "analysis_collaboration_node"
    if step.startswith("speak:"):
        agent_name = agent_from_step(step)
        return {
            "LogAgent": "log_agent_node",
            "DomainAgent": "domain_agent_node",
            "CodeAgent": "code_agent_node",
            "CriticAgent": "critic_agent_node",
            "RebuttalAgent": "rebuttal_agent_node",
            "JudgeAgent": "judge_agent_node",
        }.get(agent_name, "round_evaluate")
    return {
        "critic": "critic_agent_node",
        "rebuttal": "rebuttal_agent_node",
        "judge": "judge_agent_node",
    }.get(step, "round_evaluate")


def recent_agent_card(round_cards: List[AgentEvidence], agent_name: str) -> Optional[AgentEvidence]:
    target = str(agent_name or "").strip()
    if not target:
        return None
    for card in reversed(round_cards):
        if str(card.agent_name or "").strip() == target:
            return card
    return None


def recent_judge_card(round_cards: List[AgentEvidence]) -> Optional[AgentEvidence]:
    return recent_agent_card(round_cards, "JudgeAgent")


def round_agent_counts(round_cards: List[AgentEvidence]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for card in round_cards:
        name = str(card.agent_name or "").strip()
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def judge_is_ready(
    round_cards: List[AgentEvidence],
    *,
    parallel_analysis_agents: Sequence[str],
    debate_enable_critique: bool,
) -> bool:
    seen = {str(card.agent_name or "").strip() for card in round_cards}
    if not all(name in seen for name in parallel_analysis_agents):
        return False
    if debate_enable_critique:
        return "CriticAgent" in seen and "RebuttalAgent" in seen
    return True


def route_guardrail(
    *,
    state: Dict[str, Any],
    round_cards: List[AgentEvidence],
    route_decision: Dict[str, Any],
    consensus_threshold: float,
    max_discussion_steps_default: int,
    parallel_analysis_agents: Sequence[str],
    debate_enable_critique: bool,
) -> Dict[str, Any]:
    """Constrain supervisor routing to avoid low-signal loops."""
    next_step = str(route_decision.get("next_step") or "").strip()
    if not next_step:
        return route_decision
    if bool(route_decision.get("should_stop") or False):
        return route_decision

    judge_card = recent_judge_card(round_cards)
    judge_output = _agent_output_from_state(state, "JudgeAgent")
    judge_confidence = _output_confidence(judge_output, default=float((judge_card.confidence if judge_card else 0.0) or 0.0))
    if judge_confidence >= consensus_threshold:
        return {
            **route_decision,
            "next_step": "",
            "should_stop": True,
            "stop_reason": "JudgeAgent 已给出高置信裁决",
            "reason": "路由守卫：已有高置信裁决，终止讨论",
        }

    ready_from_cards = judge_is_ready(
        round_cards,
        parallel_analysis_agents=parallel_analysis_agents,
        debate_enable_critique=debate_enable_critique,
    )
    state_seen = set()
    outputs = state.get("agent_outputs")
    if isinstance(outputs, dict):
        state_seen = {str(name or "").strip() for name in outputs.keys() if str(name or "").strip()}
    ready_from_state = all(name in state_seen for name in parallel_analysis_agents) and (
        (not debate_enable_critique) or ("CriticAgent" in state_seen and "RebuttalAgent" in state_seen)
    )
    if not (ready_from_cards or ready_from_state):
        return route_decision

    discussion_step_count = int(state.get("discussion_step_count") or 0)
    max_discussion_steps = int(state.get("max_discussion_steps") or max_discussion_steps_default)
    target_agent = agent_from_step(next_step)
    counts = round_agent_counts(round_cards)
    recent_agents = [str(card.agent_name or "") for card in round_cards[-4:]]
    commander_card = recent_agent_card(round_cards, "ProblemAnalysisAgent")
    commander_output = _agent_output_from_state(state, "ProblemAnalysisAgent")
    if not commander_output and commander_card and isinstance(getattr(commander_card, "raw_output", None), dict):
        commander_output = commander_card.raw_output
    commander_confidence = _output_confidence(
        commander_output,
        default=float(getattr(commander_card, "confidence", 0.0) or 0.0),
    )
    unresolved_items: List[str] = []
    for key in ("open_questions", "missing_info", "needs_validation"):
        value = commander_output.get(key)
        if isinstance(value, list):
            unresolved_items.extend([str(v or "").strip() for v in value if str(v or "").strip()])
        elif isinstance(value, str) and value.strip():
            unresolved_items.append(value.strip())
    unresolved_count = len(list(dict.fromkeys(unresolved_items)))

    near_budget = discussion_step_count >= max(4, max_discussion_steps - 4)
    repeated_target = bool(target_agent) and counts.get(target_agent, 0) >= 2
    repeated_recent = len(recent_agents) >= 3 and len(set(recent_agents[-3:])) <= 2
    rebuttal_done = counts.get("RebuttalAgent", 0) >= 1
    critic_done = counts.get("CriticAgent", 0) >= 1
    requested_parallel_again = next_step in ("analysis_parallel", "parallel_analysis")
    post_rebuttal_settle = (
        judge_card is None
        and rebuttal_done
        and (not debate_enable_critique or critic_done)
        and discussion_step_count >= 8
        and (target_agent not in ("JudgeAgent", "") or requested_parallel_again)
    )
    critique_cycle_cap = (
        judge_card is None
        and debate_enable_critique
        and rebuttal_done
        and critic_done
        and discussion_step_count >= 9
        and counts.get("ProblemAnalysisAgent", 0) >= 4
        and requested_parallel_again
    )
    commander_prefers_settle = (
        judge_card is None
        and discussion_step_count >= 5
        and target_agent not in ("JudgeAgent", "")
        and commander_confidence >= 0.78
        and unresolved_count == 0
    )
    no_critique_revisit_cap = (
        judge_card is None
        and not debate_enable_critique
        and discussion_step_count >= 6
        and target_agent in set(parallel_analysis_agents)
        and counts.get("ProblemAnalysisAgent", 0) >= 3
        and counts.get(target_agent or "", 0) >= 2
        and commander_confidence >= 0.65
    )
    if judge_card is None and (
        near_budget
        or (discussion_step_count >= 6 and repeated_target)
        or (discussion_step_count >= 7 and repeated_recent)
        or post_rebuttal_settle
        or critique_cycle_cap
        or commander_prefers_settle
        or no_critique_revisit_cap
    ):
        if critique_cycle_cap:
            guardrail_reason = "路由守卫：批判/反驳链已完成，禁止再次并行拉取专家，切换 JudgeAgent 裁决"
        elif commander_prefers_settle:
            guardrail_reason = "路由守卫：主Agent已给出较高置信且无未决问题，切换 JudgeAgent 收敛裁决"
        elif no_critique_revisit_cap:
            guardrail_reason = "路由守卫：无批判环节模式下专家重复补充已达上限，切换 JudgeAgent 裁决"
        else:
            guardrail_reason = "路由守卫：证据已覆盖核心维度，切换 JudgeAgent 收敛裁决"
        return {
            **route_decision,
            "next_step": step_for_agent("JudgeAgent"),
            "should_stop": False,
            "stop_reason": "",
            "reason": guardrail_reason,
        }

    return route_decision


def fallback_supervisor_route(
    *,
    state: Dict[str, Any],
    round_cards: List[AgentEvidence],
    debate_enable_critique: bool,
    consensus_threshold: float,
    max_discussion_steps_default: int,
    parallel_analysis_agents: Sequence[str],
) -> Dict[str, Any]:
    seen_agents = [card.agent_name for card in round_cards]
    seen_set = {str(name or "").strip() for name in seen_agents if str(name or "").strip()}
    outputs = state.get("agent_outputs")
    if isinstance(outputs, dict):
        seen_set.update({str(name or "").strip() for name in outputs.keys() if str(name or "").strip()})
    discussion_step_count = int(state.get("discussion_step_count") or 0)
    max_steps = int(state.get("max_discussion_steps") or max_discussion_steps_default)
    judge_card = recent_judge_card(round_cards)
    judge_output = _agent_output_from_state(state, "JudgeAgent")
    judge_conf = _output_confidence(judge_output, default=float(judge_card.confidence or 0.0) if judge_card else 0.0)

    if not all(name in seen_set for name in parallel_analysis_agents):
        return {
            "next_step": "analysis_parallel",
            "reason": "分析三专家尚未全部发言，先并行收集证据",
            "should_stop": False,
            "stop_reason": "",
        }

    if debate_enable_critique and "CriticAgent" not in seen_set:
        return {
            "next_step": step_for_agent("CriticAgent"),
            "reason": "进入质疑环节补证据缺口",
            "should_stop": False,
            "stop_reason": "",
        }

    if debate_enable_critique and "CriticAgent" in seen_set and "RebuttalAgent" not in seen_set:
        return {
            "next_step": step_for_agent("RebuttalAgent"),
            "reason": "需要回应质疑并补充证据",
            "should_stop": False,
            "stop_reason": "",
        }

    if judge_card is None and not judge_output:
        return {
            "next_step": step_for_agent("JudgeAgent"),
            "reason": "已收集主要观点，进入裁决汇总",
            "should_stop": False,
            "stop_reason": "",
        }

    if judge_conf >= consensus_threshold:
        return {
            "next_step": "",
            "reason": "JudgeAgent 置信度达到阈值，可结束本轮",
            "should_stop": True,
            "stop_reason": "证据充分且已形成裁决",
        }

    if discussion_step_count >= max_steps:
        return {
            "next_step": step_for_agent("JudgeAgent"),
            "reason": "达到讨论步数预算，要求 JudgeAgent 最终裁决",
            "should_stop": False,
            "stop_reason": "",
        }

    cycle = ["LogAgent", "CodeAgent", "DomainAgent"]
    for candidate in cycle:
        if seen_agents and seen_agents[-1] == candidate:
            continue
        return {
            "next_step": step_for_agent(candidate),
            "reason": "继续围绕未决问题补充专家证据",
            "should_stop": False,
            "stop_reason": "",
        }
    return {
        "next_step": step_for_agent("JudgeAgent"),
        "reason": "回退到 JudgeAgent 汇总裁决",
        "should_stop": False,
        "stop_reason": "",
    }


def route_from_commander_output(
    *,
    payload: Dict[str, Any],
    state: Dict[str, Any],
    round_cards: List[AgentEvidence],
    allowed_agents: Sequence[str],
    is_placeholder_summary: Any,
    fallback_supervisor_route_fn: Any,
    route_guardrail_fn: Any,
) -> Dict[str, Any]:
    next_mode = str(payload.get("next_mode") or "").strip().lower()
    next_agent = str(payload.get("next_agent") or "").strip()
    should_stop = bool(payload.get("should_stop") or False)
    stop_reason = str(payload.get("stop_reason") or "").strip()

    allowed_agent_set = {str(name or "").strip() for name in allowed_agents if str(name or "").strip()}
    if next_agent and next_agent not in allowed_agent_set:
        next_agent = ""

    next_step = ""
    if next_mode in ("parallel_analysis", "analysis_parallel"):
        next_step = "analysis_parallel"
    elif next_mode == "judge":
        next_step = step_for_agent("JudgeAgent")
    elif next_mode == "single" and next_agent:
        next_step = step_for_agent(next_agent)
    elif next_mode == "stop":
        next_step = ""
        should_stop = True
    elif next_agent:
        next_step = step_for_agent(next_agent)

    if should_stop:
        judge_card = recent_judge_card(round_cards)
        judge_output = _agent_output_from_state(state, "JudgeAgent")
        judge_available = bool(judge_card) or bool(judge_output)
        if not judge_available:
            next_step = step_for_agent("JudgeAgent")
            should_stop = False
            if not stop_reason:
                stop_reason = "主Agent请求停止，但尚无裁决，先触发 JudgeAgent 汇总"
        else:
            source = (
                judge_card.raw_output
                if judge_card and isinstance(getattr(judge_card, "raw_output", None), dict)
                else judge_output
            )
            summary = str((((source or {}).get("final_judgment", {})).get("root_cause", {})).get("summary", ""))
            if is_placeholder_summary(summary):
                next_step = step_for_agent("JudgeAgent")
                should_stop = False
                stop_reason = "JudgeAgent 结论仍为占位，继续裁决一次"

    if not next_step and not should_stop:
        return fallback_supervisor_route_fn(state=state, round_cards=round_cards)

    return route_guardrail_fn(
        state=state,
        round_cards=round_cards,
        route_decision={
            "next_step": next_step,
            "should_stop": should_stop,
            "stop_reason": stop_reason,
            "reason": "主Agent动态调度决策",
        },
    )
