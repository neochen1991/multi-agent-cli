"""Typed state and lightweight runtime models for LangGraph orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import MessagesState


class DebateMessagesState(MessagesState, total=False):
    """LangGraph-style shared conversation state."""


class DebateExecState(DebateMessagesState, total=False):
    context: Dict[str, Any]
    context_summary: Dict[str, Any]
    history_cards: List[Any]
    claims: List[Dict[str, Any]]
    open_questions: List[str]
    agent_outputs: Dict[str, Dict[str, Any]]
    consensus_reached: bool
    executed_rounds: int
    current_round: int
    continue_next_round: bool
    agent_commands: Dict[str, Dict[str, Any]]
    next_step: str
    round_start_turn_index: int
    discussion_step_count: int
    max_discussion_steps: int
    supervisor_stop_requested: bool
    supervisor_stop_reason: str
    supervisor_notes: List[Dict[str, Any]]
    final_payload: Dict[str, Any]


@dataclass
class DebateTurn:
    round_number: int
    phase: str
    agent_name: str
    agent_role: str
    model: Dict[str, str]
    input_message: str
    output_content: Dict[str, Any]
    confidence: float
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    phase: str
    system_prompt: str
