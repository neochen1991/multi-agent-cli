"""Routing rule engine for LangGraph debate runtime.

The rule engine evaluates routing rules in priority order and returns
the first matching decision.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from app.runtime.langgraph.routing.rules import RoutingContext, RoutingDecision, RoutingRule

logger = structlog.get_logger()


class RoutingRuleEngine:
    """Evaluates routing rules in priority order.

    The engine maintains a sorted list of rules and evaluates them
    in order of priority (lower number = higher priority).
    """

    def __init__(self, rules: Optional[List[RoutingRule]] = None):
        """
        Args:
            rules: Optional list of rules to initialize with.
                   If None, uses default rules.
        """
        self._rules: List[RoutingRule] = []
        if rules is not None:
            for rule in rules:
                self.add_rule(rule)
        else:
            for rule in self._default_rules():
                self.add_rule(rule)

    def _default_rules(self) -> List[RoutingRule]:
        """Create default rule set.

        Import here to avoid circular imports.
        """
        from app.runtime.langgraph.routing.rules_impl import (
            BudgetRule,
            CommanderSettleRule,
            ConsensusRule,
            CritiqueCycleRule,
            JudgeReadyRule,
            NoCritiqueRevisitRule,
            PostRebuttalSettleRule,
            RepetitionRule,
        )

        return [
            # Highest priority: Check for consensus first
            ConsensusRule(priority=10),
            # Check if judge is ready to make a decision
            JudgeReadyRule(priority=15),
            # Budget constraints
            BudgetRule(priority=20),
            # Repetition detection
            RepetitionRule(priority=30),
            # Critique cycle management
            CritiqueCycleRule(priority=40),
            PostRebuttalSettleRule(priority=45),
            # Commander confidence-based decisions
            CommanderSettleRule(priority=50),
            NoCritiqueRevisitRule(priority=55),
        ]

    def add_rule(self, rule: RoutingRule) -> None:
        """Add a rule to the engine, maintaining priority order.

        Args:
            rule: The rule to add.
        """
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)
        logger.debug(
            "routing_rule_added",
            rule_name=rule.name,
            rule_priority=rule.priority,
            total_rules=len(self._rules),
        )

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name.

        Args:
            name: The name of the rule to remove.

        Returns:
            True if the rule was found and removed, False otherwise.
        """
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                self._rules.pop(i)
                logger.debug(
                    "routing_rule_removed",
                    rule_name=name,
                    remaining_rules=len(self._rules),
                )
                return True
        return False

    def get_rule(self, name: str) -> Optional[RoutingRule]:
        """Get a rule by name.

        Args:
            name: The name of the rule to find.

        Returns:
            The rule if found, None otherwise.
        """
        for rule in self._rules:
            if rule.name == name:
                return rule
        return None

    def enable_rule(self, name: str) -> bool:
        """Enable a rule by name.

        Args:
            name: The name of the rule to enable.

        Returns:
            True if the rule was found and enabled, False otherwise.
        """
        rule = self.get_rule(name)
        if rule and hasattr(rule, "_enabled"):
            rule._enabled = True  # type: ignore
            return True
        return False

    def disable_rule(self, name: str) -> bool:
        """Disable a rule by name.

        Args:
            name: The name of the rule to disable.

        Returns:
            True if the rule was found and disabled, False otherwise.
        """
        rule = self.get_rule(name)
        if rule and hasattr(rule, "_enabled"):
            rule._enabled = False  # type: ignore
            return True
        return False

    def evaluate(self, ctx: RoutingContext) -> RoutingDecision:
        """Evaluate all rules in priority order.

        Returns the decision from the first matching rule.
        If no rule matches, returns a default decision to continue.

        Args:
            ctx: The routing context.

        Returns:
            A RoutingDecision indicating the next action.
        """
        for rule in self._rules:
            if not rule.enabled:
                continue

            try:
                decision = rule.evaluate(ctx)
                if decision is not None:
                    logger.info(
                        "routing_rule_matched",
                        rule=rule.name,
                        priority=rule.priority,
                        next_step=decision.next_step,
                        should_stop=decision.should_stop,
                        reason=decision.reason,
                    )
                    return decision
            except Exception as e:
                logger.error(
                    "routing_rule_error",
                    rule=rule.name,
                    error=str(e),
                    exc_info=True,
                )
                # Continue to next rule on error

        # Default: continue with the proposed next step
        return RoutingDecision(
            next_step=ctx.next_step,
            should_stop=False,
            stop_reason="",
            reason="No matching rule, continue with proposed step",
        )

    def evaluate_from_state(
        self,
        state: Dict[str, Any],
        route_decision: Dict[str, Any],
        consensus_threshold: float,
        max_discussion_steps_default: int,
        parallel_analysis_agents: List[str],
        debate_enable_critique: bool,
        round_cards: List[Any],
    ) -> Dict[str, Any]:
        """Build context from state and evaluate rules.

        This is a convenience method for integrating with existing code.

        Args:
            state: The current debate state.
            route_decision: The proposed routing decision.
            consensus_threshold: Confidence threshold for consensus.
            max_discussion_steps_default: Default max discussion steps.
            parallel_analysis_agents: List of parallel analysis agents.
            debate_enable_critique: Whether critique is enabled.
            round_cards: Cards from the current round.

        Returns:
            A dictionary with the routing decision.
        """
        from app.runtime.langgraph.routing import (
            agent_from_step,
            judge_is_ready,
            recent_agent_card,
            recent_judge_card,
            round_agent_counts,
        )

        # Extract context from state
        discussion_step = int(state.get("discussion_step_count") or 0)
        max_steps = int(state.get("max_discussion_steps") or max_discussion_steps_default)
        next_step = str(route_decision.get("next_step") or "").strip()
        target_agent = agent_from_step(next_step)

        # Get judge information
        judge_card = recent_judge_card(round_cards)
        judge_output = state.get("agent_outputs", {}).get("JudgeAgent", {})
        judge_confidence = float(
            (judge_output.get("confidence") or 0.0)
            or (getattr(judge_card, "confidence", 0.0) if judge_card else 0.0)
        )

        # Get commander information
        commander_card = recent_agent_card(round_cards, "ProblemAnalysisAgent")
        commander_output = state.get("agent_outputs", {}).get("ProblemAnalysisAgent", {})
        if not commander_output and commander_card:
            commander_output = getattr(commander_card, "raw_output", {}) or {}
        commander_confidence = float(
            (commander_output.get("confidence") or 0.0)
            or (getattr(commander_card, "confidence", 0.0) if commander_card else 0.0)
        )

        # Count unresolved items
        unresolved_items: List[str] = []
        for key in ("open_questions", "missing_info", "needs_validation"):
            value = commander_output.get(key)
            if isinstance(value, list):
                unresolved_items.extend([str(v or "").strip() for v in value if str(v or "").strip()])
            elif isinstance(value, str) and value.strip():
                unresolved_items.append(value.strip())
        unresolved_count = len(list(dict.fromkeys(unresolved_items)))

        # Build context
        ctx = RoutingContext(
            state=state,
            discussion_step=discussion_step,
            max_steps=max_steps,
            round_cards=round_cards,
            agent_counts=round_agent_counts(round_cards),
            judge_confidence=judge_confidence,
            judge_card=judge_card,
            commander_confidence=commander_confidence,
            commander_output=commander_output,
            unresolved_count=unresolved_count,
            target_agent=target_agent,
            next_step=next_step,
            debate_enable_critique=debate_enable_critique,
            parallel_analysis_agents=parallel_analysis_agents,
        )

        # Evaluate rules
        decision = self.evaluate(ctx)

        # Merge with original decision
        result = dict(route_decision)
        result.update(decision.to_dict())
        return result

    @property
    def rules(self) -> List[RoutingRule]:
        """Get the list of rules (read-only)."""
        return list(self._rules)


__all__ = ["RoutingRuleEngine"]