"""Routing module for LangGraph debate runtime.

This module provides a strategy pattern implementation for routing decisions,
replacing the monolithic route_guardrail function with composable rules.
"""

from app.runtime.langgraph.routing.rules import (
    CompositeRule,
    RoutingContext,
    RoutingDecision,
    RoutingRule,
)
from app.runtime.langgraph.routing.rule_engine import RoutingRuleEngine
from app.runtime.langgraph.routing.rules_impl import (
    BudgetRule,
    CommanderSettleRule,
    ConsensusRule,
    CritiqueCycleRule,
    JudgeCoverageRule,
    JudgeReadyRule,
    NoCritiqueRevisitRule,
    PostRebuttalSettleRule,
    RepetitionRule,
)

# Re-export helper functions from original routing.py
from app.runtime.langgraph.routing_helpers import (
    _agent_output_from_state,
    _output_confidence,
    _recent_agent_card,
    agent_from_step,
    fallback_supervisor_route,
    judge_is_ready,
    recent_agent_card,
    recent_judge_card,
    round_agent_counts,
    route_from_commander_output,
    route_guardrail,
    step_for_agent,
    supervisor_step_to_node,
)

__all__ = [
    # Core classes
    "RoutingContext",
    "RoutingDecision",
    "RoutingRule",
    "CompositeRule",
    "RoutingRuleEngine",
    # Concrete rules
    "ConsensusRule",
    "JudgeReadyRule",
    "BudgetRule",
    "RepetitionRule",
    "CritiqueCycleRule",
    "PostRebuttalSettleRule",
    "CommanderSettleRule",
    "NoCritiqueRevisitRule",
    "JudgeCoverageRule",
    # Helper functions
    "_agent_output_from_state",
    "_output_confidence",
    "_recent_agent_card",
    "agent_from_step",
    "fallback_supervisor_route",
    "judge_is_ready",
    "recent_agent_card",
    "recent_judge_card",
    "round_agent_counts",
    "route_from_commander_output",
    "route_guardrail",
    "step_for_agent",
    "supervisor_step_to_node",
]