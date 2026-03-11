"""Concrete routing rule implementations for LangGraph debate runtime.

This module contains the specific routing rules extracted from the original
route_guardrail function.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.runtime.langgraph.routing.rules import (
    RoutingContext,
    RoutingDecision,
    RoutingRule,
)
from app.runtime.langgraph.routing_helpers import (
    _agent_has_effective_evidence,
    _gap_target_agent,
    infer_relevant_agents_from_texts,
)
from app.runtime.messages import AgentEvidence


def _output_confidence(payload: Dict[str, Any], default: float = 0.0) -> float:
    """Extract confidence from an agent output payload."""
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


def _recent_agent_card(round_cards: List[AgentEvidence], agent_name: str) -> Optional[AgentEvidence]:
    """Get the most recent card for a specific agent."""
    target = str(agent_name or "").strip()
    if not target:
        return None
    for card in reversed(round_cards):
        if str(card.agent_name or "").strip() == target:
            return card
    return None


def step_for_agent(agent_name: str) -> str:
    """Convert an agent name to a step string."""
    return f"speak:{str(agent_name or '').strip()}"


def _has_effective_parallel_coverage(ctx: RoutingContext) -> bool:
    """判断当前并行分析专家是否已经形成足够的有效覆盖。"""
    parallel_agents = [str(name or "").strip() for name in list(ctx.parallel_analysis_agents or []) if str(name or "").strip()]
    if not parallel_agents:
        return False

    agent_outputs = ctx.state.get("agent_outputs", {}) if isinstance(ctx.state.get("agent_outputs"), dict) else {}
    effective_count = 0
    for agent_name in parallel_agents:
        # 先从 round card 读最新证据；没有就退回 state 里的结构化输出。
        card = _recent_agent_card(ctx.round_cards, agent_name)
        payload = getattr(card, "raw_output", {}) if card else {}
        if not isinstance(payload, dict) or not payload:
            payload = agent_outputs.get(agent_name, {}) if isinstance(agent_outputs.get(agent_name), dict) else {}
        if not isinstance(payload, dict) or not payload:
            return False
        conclusion = str(payload.get("conclusion") or getattr(card, "conclusion", "") or "").strip()
        evidence_chain = payload.get("evidence_chain")
        has_evidence = isinstance(evidence_chain, list) and len(evidence_chain) > 0
        confidence = _output_confidence(payload, default=float(getattr(card, "confidence", 0.0) or 0.0))
        degraded = bool(payload.get("degraded")) or str(payload.get("evidence_status") or "").strip().lower() in {
            "degraded",
            "missing",
            "inferred_without_tool",
        }
        if degraded or confidence < 0.55 or not (conclusion or has_evidence):
            return False
        effective_count += 1

    # 至少要有 3 个分析专家形成有效结论，才值得直接交给 Judge。
    return effective_count >= min(3, len(parallel_agents))


def _looks_like_quick_route_miss(ctx: RoutingContext) -> bool:
    """识别 quick 模式下“网关本地路由缺失”的收口型场景。"""
    mode = str(ctx.state.get("execution_mode") or ctx.state.get("analysis_depth_mode") or "").strip().lower()
    if mode != "quick":
        return False

    incident = ctx.state.get("incident") if isinstance(ctx.state.get("incident"), dict) else {}
    merged_text = " ".join(
        [
            str(incident.get("title") or ""),
            str(incident.get("description") or ""),
            str(ctx.state.get("log_excerpt") or ""),
        ]
    ).lower()
    route_tokens = ("404", "route", "路由", "not found", "gateway", "网关")
    return any(token in merged_text for token in route_tokens)


def _supports_gateway_local_404(payload: Dict[str, Any]) -> bool:
    """判断输出是否已经指向“404 发生在网关本地，未转发到下游”这一关键信号。"""
    if not isinstance(payload, dict):
        return False
    merged_text = " ".join(
        [
            str(payload.get("conclusion") or ""),
            " ".join(str(item or "") for item in list(payload.get("evidence_chain") or [])),
        ]
    ).lower()
    required_any = ("route not found", "gateway route", "route lookup", "未转发到下游", "本地路由", "网关")
    return "404" in merged_text and any(token in merged_text for token in required_any)


def _rules_out_database_as_primary(payload: Dict[str, Any]) -> bool:
    """判断数据库专家是否已经给出“数据库不是主因”的排除性结论。"""
    if not isinstance(payload, dict):
        return False
    conclusion = str(payload.get("conclusion") or "").strip().lower()
    if not conclusion:
        return False
    return ("数据库" in conclusion or "db" in conclusion) and any(
        token in conclusion for token in ("不是", "非", "not", "排除", "主因")
    )


class ConsensusRule(RoutingRule):
    """Rule that stops execution when judge confidence reaches threshold."""

    def __init__(self, threshold: float = 0.85, priority: int = 10):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._threshold = threshold
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "consensus"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.judge_confidence >= self._threshold:
            if "VerificationAgent" not in ctx.seen_agents:
                return RoutingDecision(
                    next_step=step_for_agent("VerificationAgent"),
                    should_stop=False,
                    stop_reason="",
                    reason="Judge 置信度达标，但尚未生成验证计划",
                    metadata={"confidence": ctx.judge_confidence, "threshold": self._threshold},
                )
            return RoutingDecision(
                next_step="",
                should_stop=True,
                stop_reason="JudgeAgent 已给出高置信裁决",
                reason=f"JudgeAgent置信度({ctx.judge_confidence:.2f})达到阈值({self._threshold})",
                metadata={"confidence": ctx.judge_confidence, "threshold": self._threshold},
            )
        return None


class JudgeReadyRule(RoutingRule):
    """Rule that checks if judge should be invoked based on agent coverage."""

    def __init__(self, priority: int = 15):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "judge_ready"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        # Check if all required agents have spoken
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        seen = ctx.seen_agents
        parallel_agents = set(ctx.parallel_analysis_agents)

        if not all(name in seen for name in parallel_agents):
            return None

        if ctx.debate_enable_critique:
            if "CriticAgent" not in seen or "RebuttalAgent" not in seen:
                return None

        # Check if judge has already spoken
        if ctx.judge_card is not None:
            return None

        # Judge is ready but hasn't spoken - let normal routing handle this
        return None


class BudgetRule(RoutingRule):
    """Rule that forces judge decision when approaching step budget."""

    def __init__(self, threshold_ratio: float = 0.8, priority: int = 20):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._threshold_ratio = threshold_ratio
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "budget"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        # Only apply if judge hasn't decided yet
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.judge_card is not None:
            return None

        near_budget = ctx.discussion_step >= max(4, int(ctx.max_steps * self._threshold_ratio))

        if near_budget and ctx.judge_confidence < 0.5:
            return RoutingDecision(
                next_step=step_for_agent("JudgeAgent"),
                should_stop=False,
                reason=f"接近步数预算({ctx.discussion_step}/{ctx.max_steps})，切换JudgeAgent裁决",
                metadata={
                    "discussion_step": ctx.discussion_step,
                    "max_steps": ctx.max_steps,
                },
            )

        return None


class RepetitionRule(RoutingRule):
    """Rule that detects and breaks agent repetition patterns."""

    def __init__(
        self,
        max_repeats: int = 2,
        recent_window: int = 3,
        priority: int = 30,
    ):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._max_repeats = max_repeats
        self._recent_window = recent_window
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "repetition"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.judge_card is not None:
            return None

        # Check if target agent is being repeated
        if ctx.target_agent:
            count = ctx.agent_counts.get(ctx.target_agent, 0)
            if count >= self._max_repeats and ctx.discussion_step >= 6:
                return RoutingDecision(
                    next_step=step_for_agent("JudgeAgent"),
                    should_stop=False,
                    reason=f"Agent {ctx.target_agent} 已重复执行{count}次，切换JudgeAgent",
                    metadata={"target_agent": ctx.target_agent, "count": count},
                )

        # Check recent agent repetition
        recent = ctx.recent_agents
        if len(recent) >= self._recent_window:
            unique_recent = len(set(recent[-self._recent_window:]))
            if unique_recent <= 2 and ctx.discussion_step >= 7:
                return RoutingDecision(
                    next_step=step_for_agent("JudgeAgent"),
                    should_stop=False,
                    reason="检测到Agent重复发言模式，强制切换JudgeAgent",
                    metadata={"recent_agents": recent[-self._recent_window:]},
                )

        return None


class CritiqueCycleRule(RoutingRule):
    """Rule that prevents infinite loops after critique cycle is complete."""

    def __init__(self, min_steps: int = 9, min_commander_calls: int = 4, priority: int = 40):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._min_steps = min_steps
        self._min_commander_calls = min_commander_calls
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "critique_cycle"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if not ctx.debate_enable_critique:
            return None

        if ctx.judge_card is not None:
            return None

        rebuttal_done = ctx.agent_counts.get("RebuttalAgent", 0) >= 1
        critic_done = ctx.agent_counts.get("CriticAgent", 0) >= 1
        commander_calls = ctx.agent_counts.get("ProblemAnalysisAgent", 0)

        requested_parallel = ctx.next_step in ("analysis_parallel", "parallel_analysis")

        if (
            rebuttal_done
            and critic_done
            and ctx.discussion_step >= self._min_steps
            and commander_calls >= self._min_commander_calls
            and requested_parallel
        ):
            return RoutingDecision(
                next_step=step_for_agent("JudgeAgent"),
                should_stop=False,
                reason="批判/反驳链已完成，禁止再次并行拉取专家，切换JudgeAgent裁决",
                metadata={
                    "rebuttal_done": rebuttal_done,
                    "critic_done": critic_done,
                    "commander_calls": commander_calls,
                },
            )

        return None


class PostRebuttalSettleRule(RoutingRule):
    """Rule that triggers judge after rebuttal phase."""

    def __init__(self, min_steps: int = 8, priority: int = 45):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._min_steps = min_steps
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "post_rebuttal_settle"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.judge_card is not None:
            return None

        rebuttal_done = ctx.agent_counts.get("RebuttalAgent", 0) >= 1
        critic_done = ctx.agent_counts.get("CriticAgent", 0) >= 1
        requested_parallel = ctx.next_step in ("analysis_parallel", "parallel_analysis")

        if (
            rebuttal_done
            and (not ctx.debate_enable_critique or critic_done)
            and ctx.discussion_step >= self._min_steps
            and (ctx.target_agent not in ("JudgeAgent", "") or requested_parallel)
        ):
            return RoutingDecision(
                next_step=step_for_agent("JudgeAgent"),
                should_stop=False,
                reason="反驳环节已完成，切换JudgeAgent收敛裁决",
                metadata={
                    "rebuttal_done": rebuttal_done,
                    "critic_done": critic_done,
                    "discussion_step": ctx.discussion_step,
                },
            )

        return None


class CommanderSettleRule(RoutingRule):
    """Rule that triggers judge when commander has high confidence and no unresolved items."""

    def __init__(self, min_steps: int = 5, min_confidence: float = 0.78, priority: int = 50):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._min_steps = min_steps
        self._min_confidence = min_confidence
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "commander_settle"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.judge_card is not None:
            return None

        if ctx.target_agent in ("JudgeAgent", ""):
            return None

        if ctx.discussion_step < self._min_steps:
            return None

        if ctx.commander_confidence >= self._min_confidence and ctx.unresolved_count == 0:
            return RoutingDecision(
                next_step=step_for_agent("JudgeAgent"),
                should_stop=False,
                reason=f"主Agent已给出较高置信({ctx.commander_confidence:.2f})且无未决问题，切换JudgeAgent收敛裁决",
                metadata={
                    "commander_confidence": ctx.commander_confidence,
                    "unresolved_count": ctx.unresolved_count,
                },
            )

        return None


class NoCritiqueRevisitRule(RoutingRule):
    """Rule that prevents excessive agent revisit when critique is disabled."""

    def __init__(
        self,
        min_steps: int = 6,
        min_commander_calls: int = 3,
        min_agent_repeats: int = 2,
        min_commander_confidence: float = 0.65,
        priority: int = 55,
    ):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._min_steps = min_steps
        self._min_commander_calls = min_commander_calls
        self._min_agent_repeats = min_agent_repeats
        self._min_commander_confidence = min_commander_confidence
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "no_critique_revisit"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.debate_enable_critique:
            return None

        if ctx.judge_card is not None:
            return None

        parallel_agents = set(ctx.parallel_analysis_agents)

        if ctx.target_agent not in parallel_agents:
            return None

        commander_calls = ctx.agent_counts.get("ProblemAnalysisAgent", 0)
        agent_repeats = ctx.agent_counts.get(ctx.target_agent or "", 0)

        if (
            ctx.discussion_step >= self._min_steps
            and commander_calls >= self._min_commander_calls
            and agent_repeats >= self._min_agent_repeats
            and ctx.commander_confidence >= self._min_commander_confidence
        ):
            return RoutingDecision(
                next_step=step_for_agent("JudgeAgent"),
                should_stop=False,
                reason="无批判环节模式下专家重复补充已达上限，切换JudgeAgent裁决",
                metadata={
                    "target_agent": ctx.target_agent,
                    "agent_repeats": agent_repeats,
                    "commander_calls": commander_calls,
                },
            )

        return None


class NoCritiqueGapTargetRule(RoutingRule):
    """无批判模式下，优先把重复并行改写成定向补证。"""

    def __init__(self, min_steps: int = 5, priority: int = 56):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._min_steps = min_steps
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "no_critique_gap_target"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.debate_enable_critique:
            return None
        if ctx.judge_card is not None:
            return None
        if ctx.discussion_step < self._min_steps:
            return None
        if ctx.next_step not in ("analysis_parallel", "parallel_analysis"):
            return None

        available_agents = [str(name or "").strip() for name in list(ctx.parallel_analysis_agents or []) if str(name or "").strip()]
        open_questions = [str(item or "") for item in list(ctx.state.get("open_questions") or [])]
        round_gap_summary = [str(item or "") for item in list(ctx.state.get("round_gap_summary") or [])]
        top_k_hypotheses = [
            str(item.get("conclusion") or "")
            for item in list(ctx.state.get("top_k_hypotheses") or [])
            if isinstance(item, dict)
        ]
        hinted_agents = infer_relevant_agents_from_texts(
            [*open_questions, *round_gap_summary, *top_k_hypotheses],
            available_agents=available_agents,
        )
        gap_target = ""
        for agent_name in hinted_agents:
            if not _agent_has_effective_evidence(ctx.round_cards, ctx.state, agent_name):
                gap_target = agent_name
                break
        if not gap_target:
            gap_target = _gap_target_agent(
                state=ctx.state,
                round_cards=ctx.round_cards,
                parallel_analysis_agents=ctx.parallel_analysis_agents,
            )
        if not gap_target:
            return None

        # commander 想再次整轮并行时，若缺口已明确归属到单个专家，就改成定向补证，
        # 避免把四个分析专家全部再跑一遍。
        return RoutingDecision(
            next_step=step_for_agent(gap_target),
            should_stop=False,
            reason=f"无批判模式下已定位明确证据缺口，改为定向追问 {gap_target}",
            metadata={
                "gap_target": gap_target,
                "discussion_step": ctx.discussion_step,
            },
        )


class NoCritiqueTargetedSettleRule(RoutingRule):
    """无批判模式下，若定向追问对象已形成有效覆盖，则直接切 Judge。"""

    def __init__(self, min_steps: int = 4, min_effective_key_agents: int = 3, priority: int = 56):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._min_steps = min_steps
        self._min_effective_key_agents = min_effective_key_agents
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "no_critique_targeted_settle"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.debate_enable_critique:
            return None
        if ctx.judge_card is not None:
            return None
        if ctx.discussion_step < self._min_steps:
            return None
        target_agent = str(ctx.target_agent or "").strip()
        parallel_agents = {str(name or "").strip() for name in list(ctx.parallel_analysis_agents or []) if str(name or "").strip()}
        if not target_agent or target_agent not in parallel_agents:
            return None
        if not all(agent in ctx.seen_agents for agent in parallel_agents):
            return None
        if not _agent_has_effective_evidence(ctx.round_cards, ctx.state, target_agent):
            return None

        effective_key_agents = sum(
            1
            for agent_name in ("LogAgent", "CodeAgent", "DatabaseAgent", "MetricsAgent")
            if _agent_has_effective_evidence(ctx.round_cards, ctx.state, agent_name)
        )
        if effective_key_agents < self._min_effective_key_agents:
            return None

        # 中文注释：这里拦截的是“工具补证型追问”。
        # 当并行专家已经完成发言，且至少 3 个关键证据专家都给出有效覆盖时，
        # 再回头追问一个已形成结论的专家，通常只会把 trace/SQL/代码行号补得更细，
        # 不会改变主因归属。此时直接切 Judge 更符合收敛目标。
        return RoutingDecision(
            next_step=step_for_agent("JudgeAgent"),
            should_stop=False,
            reason=f"{target_agent} 已形成有效覆盖，且关键专家证据已足够，切换JudgeAgent裁决",
            metadata={
                "target_agent": target_agent,
                "effective_key_agents": effective_key_agents,
                "discussion_step": ctx.discussion_step,
            },
        )


class NoCritiqueRouteMissSettleRule(RoutingRule):
    """无批判模式下，quick 路由缺失类故障满足最小证据链时直接交给 Judge。"""

    def __init__(self, min_steps: int = 4, priority: int = 57):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._min_steps = min_steps
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "no_critique_route_miss_settle"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.debate_enable_critique:
            return None
        if ctx.judge_card is not None:
            return None
        if ctx.discussion_step < self._min_steps:
            return None
        if ctx.next_step not in ("analysis_parallel", "parallel_analysis"):
            return None
        if not _looks_like_quick_route_miss(ctx):
            return None

        # 中文注释：这条规则只处理“网关本地 404”这一类非常窄的 quick 场景。
        # 当日志已确认请求停在 gateway route lookup，代码又确认下游端点实际存在，
        # 同时数据库专家已经给出“数据库不是主因”的排除性结论时，
        # 再追问注册中心/数据库只会补细节，不会改变根因归属，应直接切 Judge 收口。
        outputs = ctx.state.get("agent_outputs", {}) if isinstance(ctx.state.get("agent_outputs"), dict) else {}
        log_payload = outputs.get("LogAgent") if isinstance(outputs.get("LogAgent"), dict) else {}
        code_payload = outputs.get("CodeAgent") if isinstance(outputs.get("CodeAgent"), dict) else {}
        db_payload = outputs.get("DatabaseAgent") if isinstance(outputs.get("DatabaseAgent"), dict) else {}

        if not _supports_gateway_local_404(log_payload):
            return None
        if not code_payload or _output_confidence(code_payload) < 0.55:
            return None
        if not _supports_gateway_local_404(
            {
                "conclusion": str(code_payload.get("conclusion") or ""),
                "evidence_chain": list(code_payload.get("evidence_chain") or []),
            }
        ) and "endpoint exists" not in " ".join(str(item or "").lower() for item in list(code_payload.get("evidence_chain") or [])):
            return None
        if not _rules_out_database_as_primary(db_payload):
            return None

        return RoutingDecision(
            next_step=step_for_agent("JudgeAgent"),
            should_stop=False,
            reason="quick 模式下网关本地 404 证据链已闭合，停止重复补证并切换 JudgeAgent",
            metadata={
                "discussion_step": ctx.discussion_step,
                "scenario": "gateway_route_miss",
            },
        )


class NoCritiqueParallelSettleRule(RoutingRule):
    """无批判模式下，避免在已有充分分析覆盖后重复整轮并行分析。"""

    def __init__(self, min_steps: int = 4, priority: int = 57):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._min_steps = min_steps
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "no_critique_parallel_settle"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.debate_enable_critique:
            return None
        if ctx.judge_card is not None:
            return None
        if ctx.discussion_step < self._min_steps:
            return None
        if ctx.next_step not in ("analysis_parallel", "parallel_analysis"):
            return None
        if not _has_effective_parallel_coverage(ctx):
            return None

        # 当前轮已经有足够证据，再做整轮并行分析通常只会重复同一批结论。
        return RoutingDecision(
            next_step=step_for_agent("JudgeAgent"),
            should_stop=False,
            reason="无批判模式下分析专家已形成充分覆盖，停止重复并行分析并切换JudgeAgent",
            metadata={
                "discussion_step": ctx.discussion_step,
                "parallel_agents": list(ctx.parallel_analysis_agents),
            },
        )


class JudgeCoverageRule(RoutingRule):
    """Rule that ensures judge is called when all agents have participated."""

    def __init__(self, priority: int = 60):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._priority = priority

    @property
    def name(self) -> str:
        """执行name相关逻辑，并为当前模块提供可复用的处理能力。"""
        return "judge_coverage"

    @property
    def priority(self) -> int:
        """执行priority相关逻辑，并为当前模块提供可复用的处理能力。"""
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """执行evaluate相关逻辑，并为当前模块提供可复用的处理能力。"""
        if ctx.judge_card is not None:
            return None

        seen = ctx.seen_agents
        parallel_agents = set(ctx.parallel_analysis_agents)

        # All parallel agents have spoken
        if not all(name in seen for name in parallel_agents):
            return None

        # Critique phase complete if enabled
        if ctx.debate_enable_critique:
            if "CriticAgent" not in seen or "RebuttalAgent" not in seen:
                return None

        # Force judge if we're at budget and judge hasn't spoken
        if ctx.at_budget:
            return RoutingDecision(
                next_step=step_for_agent("JudgeAgent"),
                should_stop=False,
                reason="达到讨论步数预算，要求JudgeAgent最终裁决",
                metadata={
                    "discussion_step": ctx.discussion_step,
                    "max_steps": ctx.max_steps,
                },
            )

        return None


__all__ = [
    "ConsensusRule",
    "JudgeReadyRule",
    "BudgetRule",
    "RepetitionRule",
    "CritiqueCycleRule",
    "PostRebuttalSettleRule",
    "CommanderSettleRule",
    "NoCritiqueRevisitRule",
    "NoCritiqueTargetedSettleRule",
    "NoCritiqueRouteMissSettleRule",
    "NoCritiqueParallelSettleRule",
    "JudgeCoverageRule",
]
