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


class ConsensusRule(RoutingRule):
    """Rule that stops execution when judge confidence reaches threshold."""

    def __init__(self, threshold: float = 0.85, priority: int = 10):
        self._threshold = threshold
        self._priority = priority

    @property
    def name(self) -> str:
        return "consensus"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
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
        self._priority = priority

    @property
    def name(self) -> str:
        return "judge_ready"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        # Check if all required agents have spoken
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
        self._threshold_ratio = threshold_ratio
        self._priority = priority

    @property
    def name(self) -> str:
        return "budget"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        # Only apply if judge hasn't decided yet
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
        self._max_repeats = max_repeats
        self._recent_window = recent_window
        self._priority = priority

    @property
    def name(self) -> str:
        return "repetition"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
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
        self._min_steps = min_steps
        self._min_commander_calls = min_commander_calls
        self._priority = priority

    @property
    def name(self) -> str:
        return "critique_cycle"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
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
        self._min_steps = min_steps
        self._priority = priority

    @property
    def name(self) -> str:
        return "post_rebuttal_settle"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
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
        self._min_steps = min_steps
        self._min_confidence = min_confidence
        self._priority = priority

    @property
    def name(self) -> str:
        return "commander_settle"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
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
        self._min_steps = min_steps
        self._min_commander_calls = min_commander_calls
        self._min_agent_repeats = min_agent_repeats
        self._min_commander_confidence = min_commander_confidence
        self._priority = priority

    @property
    def name(self) -> str:
        return "no_critique_revisit"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
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


class JudgeCoverageRule(RoutingRule):
    """Rule that ensures judge is called when all agents have participated."""

    def __init__(self, priority: int = 60):
        self._priority = priority

    @property
    def name(self) -> str:
        return "judge_coverage"

    @property
    def priority(self) -> int:
        return self._priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
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
    "JudgeCoverageRule",
]
