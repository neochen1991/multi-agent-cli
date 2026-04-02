"""
LangGraph 运行时的纯路由辅助模块。

这个文件只负责“如何决定下一步该走到哪里”，不负责真正执行 Agent。
拆出这些函数的目的有两个：
1. 让路由规则可以单测，不必依赖完整 orchestrator。
2. 让 supervisor / fallback / guardrail 的判断逻辑保持集中，避免散落在运行时主类里。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.runtime.messages import AgentEvidence

KEY_EVIDENCE_AGENTS = ("LogAgent", "CodeAgent", "DatabaseAgent", "MetricsAgent")

def infer_relevant_agents_from_texts(
    texts: Sequence[str],
    *,
    available_agents: Sequence[str],
) -> List[str]:
    """兼容保留：历史规则可能调用该函数，但默认不再基于关键词做业务分发。"""
    _ = texts, available_agents
    return []


def _gap_target_agent(
    *,
    state: Dict[str, Any],
    round_cards: List[AgentEvidence],
    parallel_analysis_agents: Sequence[str],
) -> str:
    """根据 open_questions / top_k_hypotheses 选择最该被继续追问的专家。"""
    available_agents = [str(name or "").strip() for name in parallel_analysis_agents if str(name or "").strip()]
    if not available_agents:
        return ""

    missing_key_agents = [
        name
        for name in KEY_EVIDENCE_AGENTS
        if name in set(available_agents) and not _agent_has_effective_evidence(round_cards, state, name)
    ]
    degraded_agents = [
        name
        for name in KEY_EVIDENCE_AGENTS
        if name in set(available_agents) and _payload_is_degraded(_agent_output_from_state(state, name))
    ]
    if len(missing_key_agents) == 1:
        return missing_key_agents[0]
    if len(degraded_agents) == 1:
        return degraded_agents[0]
    # 中文注释：阶段 3 之后，guardrail 不再根据 open_questions/文本关键词替主 Agent 推断业务归属；
    # 这里只保留最弱的“单个关键证据专家缺失/降级”兜底，避免规则继续主导分发语义。
    return ""


def _agent_output_from_state(state: Dict[str, Any], agent_name: str) -> Dict[str, Any]:
    """从运行态 state 中提取某个 Agent 最近一次结构化输出。"""
    outputs = state.get("agent_outputs")
    if not isinstance(outputs, dict):
        return {}
    payload = outputs.get(str(agent_name or "").strip())
    return payload if isinstance(payload, dict) else {}


def _output_confidence(payload: Dict[str, Any], default: float = 0.0) -> float:
    """
    从 Agent 输出里提取置信度。

    这里优先读取顶层 `confidence`，其次兼容 `final_judgment.root_cause.confidence`
    这种嵌套结构，避免不同 Agent 输出形态不一致时读不到置信度。
    """
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


def _payload_is_degraded(payload: Dict[str, Any]) -> bool:
    """判断一个 Agent 输出是否已经进入降级/缺证据语义。"""
    if not isinstance(payload, dict):
        return False
    if bool(payload.get("degraded")):
        return True
    evidence_status = str(payload.get("evidence_status") or "").strip().lower()
    if evidence_status in {"degraded", "missing", "inferred_without_tool"}:
        return True
    conclusion = str(payload.get("conclusion") or "").strip().lower()
    degraded_tokens = (
        "调用超时，已降级继续",
        "调用异常，已降级继续",
        "模型鉴权失败，已降级继续",
        "模型密钥未配置，已降级继续",
        "调用被限流，已降级继续",
    )
    return any(token in conclusion for token in degraded_tokens)


def _agent_has_effective_evidence(round_cards: List[AgentEvidence], state: Dict[str, Any], agent_name: str) -> bool:
    """
    判断某个关键证据 Agent 是否已经给出“可用于裁决”的有效证据。

    判定条件不是单纯“有输出”：
    - 不能是 degraded/missing/inferred_without_tool
    - 必须有结论或证据链
    - 置信度要高于最小阈值
    """
    card = recent_agent_card(round_cards, agent_name)
    payload = card.raw_output if card and isinstance(getattr(card, "raw_output", None), dict) else {}
    if not payload:
        payload = _agent_output_from_state(state, agent_name)
    if not isinstance(payload, dict) or not payload:
        return False
    if _payload_is_degraded(payload):
        return False
    confidence = _output_confidence(payload, default=float(card.confidence or 0.0) if card else 0.0)
    evidence = payload.get("evidence_chain")
    has_evidence = isinstance(evidence, list) and len(evidence) > 0
    conclusion = str(payload.get("conclusion") or "").strip()
    return bool(conclusion or has_evidence) and confidence >= 0.35


def _extract_judge_summary(payload: Dict[str, Any]) -> str:
    """从 Judge 或主 Agent 的结构化输出里提取最适合展示/收口的总结文本。"""
    if not isinstance(payload, dict):
        return ""
    final_judgment = payload.get("final_judgment")
    if isinstance(final_judgment, dict):
        root_cause = final_judgment.get("root_cause")
        if isinstance(root_cause, dict):
            summary = str(root_cause.get("summary") or "").strip()
            if summary:
                return summary
    for key in ("conclusion", "chat_message", "summary"):
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    return ""


def _has_effective_agent_conclusion(
    round_cards: List[AgentEvidence],
    state: Dict[str, Any],
    agent_name: str,
    is_placeholder_summary: Any,
) -> bool:
    """
    判断指定 Agent 是否已经产出“不是占位语句”的有效结论。

    这个函数主要用于收口门禁：
    - Judge 已经有可靠裁决时，不应继续无意义续跑。
    - 主 Agent 已总结完成时，应允许直接结束会话。
    """
    card = recent_agent_card(round_cards, agent_name)
    payload = card.raw_output if card and isinstance(getattr(card, "raw_output", None), dict) else {}
    if not payload:
        payload = _agent_output_from_state(state, agent_name)
    if not isinstance(payload, dict) or not payload:
        return False
    if _payload_is_degraded(payload):
        return False
    summary = _extract_judge_summary(payload)
    return bool(summary) and not bool(is_placeholder_summary(summary))


def step_for_agent(agent_name: str) -> str:
    """把 Agent 名称转换成 supervisor 使用的 `speak:*` 步骤字符串。"""
    return f"speak:{str(agent_name or '').strip()}"


def agent_from_step(step: str) -> str:
    """从 `speak:*` 形式的步骤名里还原 Agent 名称。"""
    text = str(step or "").strip()
    return text.split(":", 1)[1].strip() if text.startswith("speak:") and ":" in text else ""


def supervisor_step_to_node(next_step: str) -> str:
    """
    把 supervisor 产出的抽象步骤转换成图节点名。

    supervisor 的输出是业务语义步骤，例如：
    - `analysis_parallel`
    - `critic`
    - `speak:DatabaseAgent`

    真正进入 LangGraph 时需要映射成具体 node 名称。
    """
    step = str(next_step or "").strip()
    if not step:
        return "round_evaluate"
    if step in ("analysis_parallel", "parallel_analysis"):
        return "analysis_parallel_node"
    if step == "analysis_collaboration":
        return "analysis_collaboration_node"
    if step.startswith("speak:"):
        agent_name = agent_from_step(step)
        if not agent_name:
            return "round_evaluate"
        alias = {
            "LogAgent": "log_agent_node",
            "DomainAgent": "domain_agent_node",
            "CodeAgent": "code_agent_node",
            "DatabaseAgent": "database_agent_node",
            "MetricsAgent": "metrics_agent_node",
            "ImpactAnalysisAgent": "impact_analysis_agent_node",
            "ChangeAgent": "change_agent_node",
            "RunbookAgent": "runbook_agent_node",
            "RuleSuggestionAgent": "rule_suggestion_agent_node",
            "CriticAgent": "critic_agent_node",
            "RebuttalAgent": "rebuttal_agent_node",
            "JudgeAgent": "judge_agent_node",
            "VerificationAgent": "verification_agent_node",
        }
        return alias.get(agent_name, f"{agent_name.replace('Agent', '').lower()}_agent_node")
    return {
        "critic": "critic_agent_node",
        "rebuttal": "rebuttal_agent_node",
        "judge": "judge_agent_node",
        "verification": "verification_agent_node",
    }.get(step, "round_evaluate")


def recent_agent_card(round_cards: List[AgentEvidence], agent_name: str) -> Optional[AgentEvidence]:
    """获取某个 Agent 最近一张 round card。"""
    target = str(agent_name or "").strip()
    if not target:
        return None
    for card in reversed(round_cards):
        if str(card.agent_name or "").strip() == target:
            return card
    return None


def _recent_agent_card(round_cards: List[AgentEvidence], agent_name: str) -> Optional[AgentEvidence]:
    """兼容旧调用入口，内部仍复用 `recent_agent_card`。"""
    return recent_agent_card(round_cards, agent_name)


def recent_judge_card(round_cards: List[AgentEvidence]) -> Optional[AgentEvidence]:
    """获取 JudgeAgent 最近一张 round card。"""
    return recent_agent_card(round_cards, "JudgeAgent")


def round_agent_counts(round_cards: List[AgentEvidence]) -> Dict[str, int]:
    """统计当前轮每个 Agent 出现次数，用于检测重复续跑和异常循环。"""
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
    state: Optional[Dict[str, Any]] = None,
    parallel_analysis_agents: Sequence[str],
    debate_enable_critique: bool,
) -> bool:
    """
    判断是否已经满足进入 Judge 的最小条件。

    当前策略要求：
    - 关键分析 Agent 至少都已经参与过
    - 关键证据 Agent 至少有 2 个给出有效证据
    - 如果开启 critique，则 Critic/Rebuttal 也必须完成
    """
    seen = {str(card.agent_name or "").strip() for card in round_cards}
    if not all(name in seen for name in parallel_analysis_agents):
        return False
    runtime_state = state or {}
    effective_key_agents = sum(
        1 for name in KEY_EVIDENCE_AGENTS if _agent_has_effective_evidence(round_cards, runtime_state, name)
    )
    if effective_key_agents < 2:
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
    """
    对 supervisor 的路由结果施加守卫规则，防止低价值循环。

    这里不会自己发明路由，而是在“已有 route_decision”基础上做兜底修正，例如：
    - 已有有效裁决时强制收口
    - 讨论步数过多时阻止继续发散
    - 缺证据时优先补关键证据而不是随意跳转
    """
    from app.runtime.langgraph.routing.rule_engine import RoutingRuleEngine

    # 统一委托给规则引擎，保证这里的行为和治理/测试口径一致。
    # guardrail 的职责不是替代 supervisor，而是在危险或低价值路由上兜底修正。
    engine = RoutingRuleEngine()
    return engine.evaluate_from_state(
        state=state,
        route_decision=route_decision,
        consensus_threshold=consensus_threshold,
        max_discussion_steps_default=max_discussion_steps_default,
        parallel_analysis_agents=list(parallel_analysis_agents),
        debate_enable_critique=debate_enable_critique,
        round_cards=round_cards,
    )


def fallback_supervisor_route(
    *,
    state: Dict[str, Any],
    round_cards: List[AgentEvidence],
    debate_enable_critique: bool,
    require_verification: bool = True,
    consensus_threshold: float,
    max_discussion_steps_default: int,
    parallel_analysis_agents: Sequence[str],
) -> Dict[str, Any]:
    """
    当 LLM 路由失败时，使用确定性 fallback 规则决定下一步。

    这个分支的目标不是“最聪明”，而是“可预期、可继续、可结束”：
    - 优先补尚未覆盖的关键分析 Agent
    - 满足裁决条件后进入 Judge
    - 避免在缺少信息时无限循环
    """
    # fallback 路由只在 supervisor 没给出可用 next_step 时兜底。
    # 规则保持保守：能 Judge 就 Judge，否则优先补缺失证据，再不行才继续并行分析。
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
    judge_count = 0
    for card in round_cards:
        if str(card.agent_name or "").strip() == "JudgeAgent":
            judge_count += 1

    effective_key_agents = sum(
        1 for name in KEY_EVIDENCE_AGENTS if _agent_has_effective_evidence(round_cards, state, name)
    )
    gap_target = _gap_target_agent(
        state=state,
        round_cards=round_cards,
        parallel_analysis_agents=parallel_analysis_agents,
    )

    if not all(name in seen_set for name in parallel_analysis_agents):
        if gap_target:
            return {
                "next_step": step_for_agent(gap_target),
                "reason": f"存在明确证据缺口，优先追问 {gap_target}",
                "should_stop": False,
                "stop_reason": "",
            }
        return {
            "next_step": "analysis_parallel",
            "reason": "分析三专家尚未全部发言，先并行收集证据",
            "should_stop": False,
            "stop_reason": "",
        }

    if effective_key_agents < 2:
        if gap_target:
            return {
                "next_step": step_for_agent(gap_target),
                "reason": f"关键证据不足，优先让 {gap_target} 补齐缺口",
                "should_stop": False,
                "stop_reason": "",
            }
        return {
            "next_step": "analysis_parallel",
            "reason": "关键证据Agent有效证据不足，继续补采日志/代码/数据库/指标证据",
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

    verification_available = bool(require_verification)
    verification_done = "VerificationAgent" in seen_set

    if judge_conf >= consensus_threshold and verification_available and not verification_done:
        return {
            "next_step": step_for_agent("VerificationAgent"),
            "reason": "裁决已形成，补充验证计划后再结束",
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
        if judge_card is not None or judge_output:
            if judge_conf >= max(0.55, consensus_threshold * 0.8) or judge_count >= 2:
                return {
                    "next_step": "",
                    "reason": "达到讨论步数预算且已有可用裁决，结束本轮",
                    "should_stop": True,
                    "stop_reason": "讨论预算耗尽，采用当前裁决收敛",
                }
        return {
            "next_step": step_for_agent("JudgeAgent"),
            "reason": "达到讨论步数预算，要求 JudgeAgent 最终裁决",
            "should_stop": False,
            "stop_reason": "",
        }

    if verification_available and (judge_card is not None or judge_output) and not verification_done:
        return {
            "next_step": step_for_agent("VerificationAgent"),
            "reason": "裁决后补充验证计划",
            "should_stop": False,
            "stop_reason": "",
        }

    cycle = ["LogAgent", "CodeAgent", "DatabaseAgent", "DomainAgent", "RuleSuggestionAgent"]
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
    """
    把主 Agent 的结构化路由输出转换成运行时最终使用的 route decision。

    这个阶段会叠加多层约束：
    - commander 原始意图
    - 当前状态与 round cards
    - guardrail 规则
    - fallback 路由
    """
    """Convert commander output to routing decision."""
    def _norm_agent_name(value: str) -> str:
        """把 commander 输出里的 Agent 名称归一化成系统标准名称。"""
        text = str(value or "").strip()
        if not text:
            return ""
        compact = text.replace("_", "").replace("-", "").replace(" ", "").lower()
        alias = {
            "logagent": "LogAgent",
            "domainagent": "DomainAgent",
            "codeagent": "CodeAgent",
            "databaseagent": "DatabaseAgent",
            "metricsagent": "MetricsAgent",
            "impactanalysisagent": "ImpactAnalysisAgent",
            "changeagent": "ChangeAgent",
            "runbookagent": "RunbookAgent",
            "rulesuggestionagent": "RuleSuggestionAgent",
            "criticagent": "CriticAgent",
            "rebuttalagent": "RebuttalAgent",
            "judgeagent": "JudgeAgent",
            "verificationagent": "VerificationAgent",
        }
        return alias.get(compact, "")

    next_mode = str(payload.get("next_mode") or "").strip().lower()
    next_agent = str(payload.get("next_agent") or "").strip()
    should_stop = bool(payload.get("should_stop") or False)
    stop_reason = str(payload.get("stop_reason") or "").strip()
    should_pause_for_review = bool(payload.get("should_pause_for_review") or False)
    review_reason = str(payload.get("review_reason") or "").strip()
    review_payload = payload.get("review_payload") if isinstance(payload.get("review_payload"), dict) else {}

    allowed_agent_set = {str(name or "").strip() for name in allowed_agents if str(name or "").strip()}
    if next_agent and next_agent not in allowed_agent_set:
        normalized = _norm_agent_name(next_agent)
        next_agent = normalized if normalized in allowed_agent_set else ""

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
        verification_done = bool(recent_agent_card(round_cards, "VerificationAgent")) or bool(
            _agent_output_from_state(state, "VerificationAgent")
        )
        if not judge_available:
            next_step = step_for_agent("JudgeAgent")
            should_stop = False
            if not stop_reason:
                stop_reason = "主Agent请求停止，但尚无裁决，先触发 JudgeAgent 汇总"
        elif "VerificationAgent" in allowed_agent_set and not verification_done:
            next_step = step_for_agent("VerificationAgent")
            should_stop = False
            if not stop_reason:
                stop_reason = "主Agent请求停止，但缺少验证计划，先触发 VerificationAgent"
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

    if not should_stop and next_step:
        next_agent_name = agent_from_step(next_step)
        judge_ready = _has_effective_agent_conclusion(
            round_cards,
            state,
            "JudgeAgent",
            is_placeholder_summary,
        )
        commander_ready = _has_effective_agent_conclusion(
            round_cards,
            state,
            "ProblemAnalysisAgent",
            is_placeholder_summary,
        )
        next_agent_card = recent_agent_card(round_cards, next_agent_name) if next_agent_name else None
        next_agent_payload = (
            next_agent_card.raw_output
            if next_agent_card and isinstance(getattr(next_agent_card, "raw_output", None), dict)
            else _agent_output_from_state(state, next_agent_name)
        )
        rerunning_degraded_agent = bool(next_agent_name) and bool(next_agent_payload) and _payload_is_degraded(next_agent_payload)
        discussion_step_count = int(state.get("discussion_step_count") or 0)
        max_steps = int(state.get("max_discussion_steps") or 0)
        near_budget_end = max_steps > 0 and discussion_step_count >= max_steps - 1
        if (
            next_agent_name
            and next_agent_name != "VerificationAgent"
            and judge_ready
            and (commander_ready or rerunning_degraded_agent or near_budget_end)
        ):
            next_step = ""
            should_stop = True
            stop_reason = stop_reason or (
                "JudgeAgent 已形成有效裁决，主Agent 已完成收敛，停止继续调度额外专家"
            )

    if should_stop:
        return {
            "next_step": "",
            "should_stop": True,
            "stop_reason": stop_reason,
            "reason": "主Agent动态调度决策",
            "should_pause_for_review": should_pause_for_review,
            "review_reason": review_reason,
            "review_payload": review_payload,
        }

    if not next_step and not should_stop:
        return fallback_supervisor_route_fn(state=state, round_cards=round_cards)

    result = route_guardrail_fn(
        state=state,
        round_cards=round_cards,
        route_decision={
            "next_step": next_step,
            "should_stop": should_stop,
            "stop_reason": stop_reason,
            "reason": "主Agent动态调度决策",
            "should_pause_for_review": should_pause_for_review,
            "review_reason": review_reason,
            "review_payload": review_payload,
        },
    )
    if should_pause_for_review:
        result["should_pause_for_review"] = True
        result["review_reason"] = review_reason
        result["review_payload"] = review_payload
        result.setdefault("resume_from_step", "report_generation")
    return result


__all__ = [
    "_agent_output_from_state",
    "_output_confidence",
    "_recent_agent_card",
    "agent_from_step",
    "fallback_supervisor_route",
    "infer_relevant_agents_from_texts",
    "judge_is_ready",
    "recent_agent_card",
    "recent_judge_card",
    "round_agent_counts",
    "route_from_commander_output",
    "route_guardrail",
    "step_for_agent",
    "supervisor_step_to_node",
]
