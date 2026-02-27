"""Routing rules interface and base classes for LangGraph debate runtime.

This module provides a strategy pattern implementation for routing decisions,
replacing the monolithic route_guardrail function with composable rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.runtime.messages import AgentEvidence


@dataclass
class RoutingContext:
    """Routing decision context containing all information needed for rule evaluation.

    This context is built from the current state and provides a clean interface
    for routing rules to make decisions without direct state access.
    """

    # Current execution state
    state: Dict[str, Any]
    discussion_step: int = 0
    max_steps: int = 12

    # Round-level information
    round_cards: List[AgentEvidence] = field(default_factory=list)
    agent_counts: Dict[str, int] = field(default_factory=dict)

    # Judge-related information
    judge_confidence: float = 0.0
    judge_card: Optional[AgentEvidence] = None

    # Commander (ProblemAnalysisAgent) related information
    commander_confidence: float = 0.0
    commander_output: Dict[str, Any] = field(default_factory=dict)
    unresolved_count: int = 0

    # Target agent for the next step
    target_agent: str = ""
    next_step: str = ""

    # Configuration flags
    debate_enable_critique: bool = True
    parallel_analysis_agents: Sequence[str] = ()

    @property
    def recent_agents(self) -> List[str]:
        """Get the list of recent agent names from round cards."""
        return [str(card.agent_name or "") for card in self.round_cards[-4:]]

    @property
    def seen_agents(self) -> set:
        """Get the set of agents that have already executed."""
        return {str(card.agent_name or "").strip() for card in self.round_cards if card.agent_name}

    @property
    def near_budget(self) -> bool:
        """Check if we're near the step budget."""
        return self.discussion_step >= max(4, self.max_steps - 4)

    @property
    def at_budget(self) -> bool:
        """Check if we're at the step budget."""
        return self.discussion_step >= self.max_steps


@dataclass
class RoutingDecision:
    """Routing decision result from rule evaluation.

    A rule returns this to indicate what action should be taken.
    If a rule doesn't apply, it returns None.
    """

    # The next step to take (e.g., "speak:LogAgent", "analysis_parallel", or "" for stop)
    next_step: str = ""

    # Whether to stop execution
    should_stop: bool = False

    # Reason for stopping (if should_stop is True)
    stop_reason: str = ""

    # Human-readable explanation for the decision
    reason: str = ""

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility with existing code."""
        return {
            "next_step": self.next_step,
            "should_stop": self.should_stop,
            "stop_reason": self.stop_reason,
            "reason": self.reason,
            **self.metadata,
        }


class RoutingRule(ABC):
    """Abstract base class for routing rules.

    Each rule encapsulates a single routing condition and its corresponding action.
    Rules are evaluated in priority order (lower priority number = evaluated first).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this rule."""
        ...

    @property
    def priority(self) -> int:
        """Rule priority (lower = higher priority). Rules with the same priority
        are evaluated in an undefined order."""
        return 100

    @property
    def enabled(self) -> bool:
        """Whether this rule is currently enabled."""
        return True

    @abstractmethod
    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        """Evaluate this rule against the context.

        Args:
            ctx: The routing context containing all decision-relevant information.

        Returns:
            A RoutingDecision if this rule applies, or None if it doesn't apply.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, priority={self.priority})"


class CompositeRule(RoutingRule):
    """A rule that combines multiple rules with AND/OR logic."""

    def __init__(
        self,
        rules: List[RoutingRule],
        name: str = "composite",
        mode: str = "and",
        priority: Optional[int] = None,
    ):
        """
        Args:
            rules: List of rules to combine.
            name: Name for this composite rule.
            mode: "and" - all rules must apply, "or" - any rule must apply.
            priority: Optional priority override.
        """
        self._rules = rules
        self._name = name
        self._mode = mode
        self._priority = priority

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority if self._priority is not None else super().priority

    def evaluate(self, ctx: RoutingContext) -> Optional[RoutingDecision]:
        results = []
        for rule in self._rules:
            result = rule.evaluate(ctx)
            if result is None and self._mode == "and":
                return None
            if result is not None:
                results.append(result)
                if self._mode == "or":
                    return result

        if self._mode == "and" and len(results) == len(self._rules):
            # Return the first non-empty decision or combine them
            return results[0] if results else None

        return None


__all__ = [
    "RoutingContext",
    "RoutingDecision",
    "RoutingRule",
    "CompositeRule",
]