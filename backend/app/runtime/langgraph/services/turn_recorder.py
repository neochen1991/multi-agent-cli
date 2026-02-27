"""Turn recorder service for LangGraph debate runtime.

This module provides turn recording and tracking functionality.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.runtime.langgraph.state import DebateTurn
from app.runtime.messages import AgentEvidence

logger = structlog.get_logger()


class TurnRecorder:
    """Records and tracks debate turns.

    This service handles:
    - Turn creation and recording
    - Turn history management
    - Turn summary generation
    """

    def __init__(self) -> None:
        """Initialize the turn recorder."""
        self._turns: List[DebateTurn] = []
        self._turn_index: Dict[int, DebateTurn] = {}  # round_number -> turn

    @property
    def turns(self) -> List[DebateTurn]:
        """Get all recorded turns."""
        return list(self._turns)

    def record(
        self,
        turn: DebateTurn,
    ) -> None:
        """Record a debate turn.

        Args:
            turn: The turn to record.
        """
        self._turns.append(turn)
        self._turn_index[turn.round_number] = turn

        logger.debug(
            "turn_recorded",
            round_number=turn.round_number,
            agent_name=turn.agent_name,
            phase=turn.phase,
        )

    def create_turn(
        self,
        *,
        agent_name: str,
        agent_role: str,
        phase: str,
        model: Dict[str, str],
        input_message: str,
        output_content: Dict[str, Any],
        confidence: float,
    ) -> DebateTurn:
        """Create a new debate turn.

        Args:
            agent_name: Name of the agent.
            agent_role: Role of the agent.
            phase: Execution phase.
            model: Model configuration.
            input_message: Input prompt.
            output_content: Output from the agent.
            confidence: Confidence score.

        Returns:
            A new DebateTurn instance.
        """
        round_number = len(self._turns) + 1
        turn = DebateTurn(
            round_number=round_number,
            phase=phase,
            agent_name=agent_name,
            agent_role=agent_role,
            model=model,
            input_message=input_message,
            output_content=output_content,
            confidence=confidence,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        return turn

    def get_turn(self, round_number: int) -> Optional[DebateTurn]:
        """Get a turn by round number.

        Args:
            round_number: The round number.

        Returns:
            The turn if found, None otherwise.
        """
        return self._turn_index.get(round_number)

    def get_turns_by_agent(self, agent_name: str) -> List[DebateTurn]:
        """Get all turns for a specific agent.

        Args:
            agent_name: The agent name.

        Returns:
            List of turns for the agent.
        """
        return [
            turn for turn in self._turns
            if turn.agent_name == agent_name
        ]

    def get_turns_by_phase(self, phase: str) -> List[DebateTurn]:
        """Get all turns for a specific phase.

        Args:
            phase: The phase name.

        Returns:
            List of turns for the phase.
        """
        return [
            turn for turn in self._turns
            if turn.phase == phase
        ]

    def get_last_turn(self) -> Optional[DebateTurn]:
        """Get the last recorded turn.

        Returns:
            The last turn, or None if no turns recorded.
        """
        if self._turns:
            return self._turns[-1]
        return None

    def get_turn_count(self) -> int:
        """Get the total number of recorded turns.

        Returns:
            The turn count.
        """
        return len(self._turns)

    def get_agent_turn_counts(self) -> Dict[str, int]:
        """Get turn counts per agent.

        Returns:
            Dictionary mapping agent names to turn counts.
        """
        counts: Dict[str, int] = {}
        for turn in self._turns:
            counts[turn.agent_name] = counts.get(turn.agent_name, 0) + 1
        return counts

    def create_fallback_turn(
        self,
        *,
        agent_name: str,
        agent_role: str,
        phase: str,
        model: Dict[str, str],
        input_message: str,
        error_text: str,
    ) -> DebateTurn:
        """Create a fallback turn for error cases.

        Args:
            agent_name: Name of the agent.
            agent_role: Role of the agent.
            phase: Execution phase.
            model: Model configuration.
            input_message: Input prompt.
            error_text: Error message.

        Returns:
            A fallback DebateTurn instance.
        """
        round_number = len(self._turns) + 1
        turn = DebateTurn(
            round_number=round_number,
            phase=phase,
            agent_name=agent_name,
            agent_role=agent_role,
            model=model,
            input_message=input_message,
            output_content={
                "conclusion": f"Agent execution failed: {error_text}",
                "error": error_text,
            },
            confidence=0.0,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        return turn

    def clear(self) -> None:
        """Clear all recorded turns."""
        self._turns.clear()
        self._turn_index.clear()

    def to_history_cards(self) -> List[AgentEvidence]:
        """Convert turns to history cards.

        Returns:
            List of AgentEvidence cards.
        """
        cards = []
        for turn in self._turns:
            card = AgentEvidence(
                agent_name=turn.agent_name,
                agent_role=turn.agent_role,
                phase=turn.phase,
                conclusion=str((turn.output_content or {}).get("conclusion") or ""),
                evidence_chain=list((turn.output_content or {}).get("evidence_chain") or []),
                confidence=turn.confidence,
                raw_output=turn.output_content,
                created_at=turn.completed_at or turn.started_at,
            )
            cards.append(card)
        return cards


__all__ = ["TurnRecorder"]