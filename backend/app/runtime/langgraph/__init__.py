"""LangGraph runtime building blocks."""

from app.runtime.langgraph.agent_runner import AgentRunner
from app.runtime.langgraph.builder import GraphBuilder
from app.runtime.langgraph.context_builders import (
    collect_peer_items_from_cards,
    collect_peer_items_from_dialogue,
    coordination_peer_items,
    history_items_for_agent_prompt,
    peer_items_for_collaboration_prompt,
    supervisor_recent_messages,
)
from app.runtime.langgraph.event_dispatcher import EventDispatcher
from app.runtime.langgraph.message_ops import (
    dedupe_new_messages,
    merge_round_and_message_cards,
    message_signature,
    messages_to_cards,
)
from app.runtime.langgraph.phase_executor import PhaseExecutor
from app.runtime.langgraph.mailbox import (
    clone_mailbox,
    compact_mailbox,
    dequeue_messages,
    enqueue_message,
)
from app.runtime.langgraph.prompt_builder import PromptBuilder
from app.runtime.langgraph.prompts import (
    build_agent_prompt,
    build_collaboration_prompt,
    build_peer_driven_prompt,
    build_problem_analysis_commander_prompt,
    build_problem_analysis_supervisor_prompt,
    coordinator_command_schema,
    judge_output_schema,
)
from app.runtime.langgraph.routing_strategy import (
    DynamicLLMRouter,
    HybridRouter,
    RoutingStrategy,
    RuleBasedRouter,
    StrategyResult,
)
from app.runtime.langgraph.specs import agent_sequence, problem_analysis_agent_spec
from app.runtime.langgraph.state import (
    AgentSpec,
    DebateExecState,
    DebateMessagesState,
    DebateTurn,
    OutputState,
    PhaseState,
    RoutingState,
    structured_state_snapshot,
    sync_structured_state,
)

__all__ = [
    # Core services
    "AgentRunner",
    "EventDispatcher",
    "PromptBuilder",
    "PhaseExecutor",
    # Builder
    "GraphBuilder",
    # Routing strategy
    "RoutingStrategy",
    "StrategyResult",
    "RuleBasedRouter",
    "DynamicLLMRouter",
    "HybridRouter",
    # Context helpers
    "collect_peer_items_from_dialogue",
    "collect_peer_items_from_cards",
    "coordination_peer_items",
    "history_items_for_agent_prompt",
    "peer_items_for_collaboration_prompt",
    "supervisor_recent_messages",
    # Message helpers
    "message_signature",
    "dedupe_new_messages",
    "messages_to_cards",
    "merge_round_and_message_cards",
    # Mailbox helpers
    "clone_mailbox",
    "enqueue_message",
    "dequeue_messages",
    "compact_mailbox",
    # State
    "AgentSpec",
    "DebateExecState",
    "DebateMessagesState",
    "DebateTurn",
    "PhaseState",
    "RoutingState",
    "OutputState",
    "structured_state_snapshot",
    "sync_structured_state",
    # Specs
    "agent_sequence",
    "problem_analysis_agent_spec",
    # Prompts
    "coordinator_command_schema",
    "judge_output_schema",
    "build_problem_analysis_commander_prompt",
    "build_problem_analysis_supervisor_prompt",
    "build_agent_prompt",
    "build_collaboration_prompt",
    "build_peer_driven_prompt",
]
