"""Agent subgraph for LangGraph parallel execution.

This module provides subgraph definitions for agent execution,
enabling native LangGraph parallel execution using the Send API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.runtime.langgraph.state import AgentSpec


class AgentSubgraphState(TypedDict, total=False):
    """State for agent subgraph execution.

    This state is used when an agent is executed as a subgraph,
    receiving only the necessary context for that specific agent.
    """

    # Agent identification
    agent_name: str
    agent_command: Optional[Dict[str, Any]]

    # Context for this agent
    loop_round: int
    context_summary: Dict[str, Any]
    history_cards: List[Any]
    dialogue_items: List[Dict[str, Any]]
    inbox_messages: List[Dict[str, Any]]

    # Output
    agent_output: Optional[Dict[str, Any]]
    updated_mailbox: Optional[Dict[str, List[Dict[str, Any]]]]

    # Reference to full state for mailbox operations
    agent_mailbox: Dict[str, List[Dict[str, Any]]]
    agent_commands: Dict[str, Dict[str, Any]]


def create_agent_subgraph_node(
    orchestrator: Any,
    agent_spec: AgentSpec,
) -> callable:
    """Create a node function for a single agent.

    This creates a node that can be executed either directly or
    as part of a parallel Send operation.

    Args:
        orchestrator: The runtime orchestrator.
        agent_spec: The agent specification.

    Returns:
        An async function that executes the agent.
    """

    async def _execute_agent(state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single agent and return the state update."""
        from app.runtime.langgraph.nodes.agents import execute_single_phase_agent
        from app.runtime.langgraph.mailbox import clone_mailbox, dequeue_messages

        agent_name = agent_spec.name
        loop_round = int(state.get("current_round") or 1)
        context_summary = state.get("context_summary") or {}
        history_cards = list(state.get("history_cards") or [])
        dialogue_items = orchestrator._dialogue_items_from_messages(
            list(state.get("messages") or []),
            limit=6,
            char_budget=720,
        )
        mailbox = clone_mailbox(state.get("agent_mailbox") or {})
        inbox_messages, mailbox = dequeue_messages(mailbox, receiver=agent_name)
        compact_context = orchestrator._compact_round_context(context_summary)

        result = await execute_single_phase_agent(
            orchestrator,
            agent_name=agent_name,
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
            agent_mailbox=mailbox,
        )

        # Build state update
        update: Dict[str, Any] = {
            "history_cards": history_cards,
        }

        mailbox = result.get("agent_mailbox")
        if mailbox:
            update["agent_mailbox"] = mailbox

        # Add message if available
        if history_cards:
            latest_message = orchestrator._card_to_ai_message(history_cards[-1])
            if latest_message is not None:
                update["messages"] = [latest_message]

        return orchestrator._graph_apply_step_result(state, update)

    return _execute_agent


def build_parallel_route_function(
    orchestrator: Any,
    parallel_agents: List[str],
) -> callable:
    """Build a routing function that returns Send objects for parallel execution.

    This function creates a router that can dispatch multiple agents
    in parallel using LangGraph's Send API.

    Args:
        orchestrator: The runtime orchestrator.
        parallel_agents: List of agent names to potentially execute in parallel.

    Returns:
        A function that returns a list of Send objects for parallel dispatch.
    """

    def route_to_parallel_agents(state: Dict[str, Any]) -> List:
        """Route to parallel agents based on agent_commands.

        This function returns Send objects for each agent that should
        be executed in parallel. It uses the agent_commands from the
        state to determine which agents to dispatch.

        Args:
            state: The current debate state.

        Returns:
            A list of Send objects (or single destination string for backward compat).
        """
        from langgraph.constants import Send

        next_step = str(state.get("next_step") or "").strip()
        agent_commands = dict(state.get("agent_commands") or {})

        # If next_step is a single agent, route to that agent
        if next_step.startswith("speak:"):
            from app.runtime.langgraph.routing import agent_from_step
            agent_name = agent_from_step(next_step)
            if agent_name:
                node_name = f"{agent_name.lower().replace('agent', '')}_agent_node"
                if agent_name == "LogAgent":
                    node_name = "log_agent_node"
                elif agent_name == "DomainAgent":
                    node_name = "domain_agent_node"
                elif agent_name == "CodeAgent":
                    node_name = "code_agent_node"
                elif agent_name == "MetricsAgent":
                    node_name = "metrics_agent_node"
                elif agent_name == "ChangeAgent":
                    node_name = "change_agent_node"
                elif agent_name == "RunbookAgent":
                    node_name = "runbook_agent_node"
                elif agent_name == "CriticAgent":
                    node_name = "critic_agent_node"
                elif agent_name == "RebuttalAgent":
                    node_name = "rebuttal_agent_node"
                elif agent_name == "JudgeAgent":
                    node_name = "judge_agent_node"
                elif agent_name == "VerificationAgent":
                    node_name = "verification_agent_node"
                return node_name

        # If next_step is parallel analysis, use Send API for true parallelism
        if next_step in ("analysis_parallel", "parallel_analysis"):
            # Determine which agents to dispatch
            target_agents = list(agent_commands.keys()) if agent_commands else parallel_agents

            # For now, we return a single node name since parallel execution
            # is handled internally by the phase_executor
            # True Send-based parallelism would require restructuring the graph
            return "analysis_parallel_node"

        # Check for other routing targets
        if next_step == "analysis_collaboration":
            return "analysis_collaboration_node"

        # Default to round evaluate
        if not next_step or state.get("supervisor_stop_requested"):
            return "round_evaluate"

        return "round_evaluate"

    return route_to_parallel_agents


def create_parallel_agent_sends(
    state: Dict[str, Any],
    agent_names: List[str],
    base_state: Dict[str, Any],
) -> List:
    """Create Send objects for parallel agent execution.

    This is a utility function that creates Send objects for each
    agent that should be executed in parallel.

    Args:
        state: The current state (used for agent-specific data).
        agent_names: List of agent names to dispatch.
        base_state: The base state to send to each agent.

    Returns:
        List of Send objects.
    """
    from langgraph.constants import Send

    sends = []
    for agent_name in agent_names:
        # Create agent-specific state
        agent_state = {
            **base_state,
            "agent_name": agent_name,
            "agent_command": (state.get("agent_commands") or {}).get(agent_name),
        }

        # Determine node name
        node_name = f"{agent_name.lower().replace('agent', '')}_agent_node"
        if agent_name == "LogAgent":
            node_name = "log_agent_node"
        elif agent_name == "DomainAgent":
            node_name = "domain_agent_node"
        elif agent_name == "CodeAgent":
            node_name = "code_agent_node"
        elif agent_name == "MetricsAgent":
            node_name = "metrics_agent_node"
        elif agent_name == "ChangeAgent":
            node_name = "change_agent_node"
        elif agent_name == "RunbookAgent":
            node_name = "runbook_agent_node"
        elif agent_name == "CriticAgent":
            node_name = "critic_agent_node"
        elif agent_name == "RebuttalAgent":
            node_name = "rebuttal_agent_node"
        elif agent_name == "JudgeAgent":
            node_name = "judge_agent_node"
        elif agent_name == "VerificationAgent":
            node_name = "verification_agent_node"

        sends.append(Send(node_name, agent_state))

    return sends


__all__ = [
    "AgentSubgraphState",
    "create_agent_subgraph_node",
    "build_parallel_route_function",
    "create_parallel_agent_sends",
]
