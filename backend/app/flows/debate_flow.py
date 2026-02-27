"""
Debate flow entrypoint.

This module keeps backward-compatible symbols while delegating execution
to the LangGraph runtime orchestrator implementation.
"""

from typing import Optional

from app.config import settings
from app.runtime.langgraph_runtime import (
    LangGraphRuntimeOrchestrator,
    DebateTurn,
)

# Backward-compatible aliases
DebateRound = DebateTurn
AIDebateOrchestrator = LangGraphRuntimeOrchestrator
LangGraphDebateOrchestrator = LangGraphRuntimeOrchestrator


def create_ai_debate_orchestrator(
    *,
    max_rounds: Optional[int] = None,
    consensus_threshold: Optional[float] = None,
) -> LangGraphRuntimeOrchestrator:
    """Create a new orchestrator instance per request to avoid shared mutable state."""
    return AIDebateOrchestrator(
        consensus_threshold=(
            float(consensus_threshold)
            if consensus_threshold is not None
            else float(settings.DEBATE_CONSENSUS_THRESHOLD)
        ),
        max_rounds=(
            int(max_rounds)
            if max_rounds is not None
            else int(settings.DEBATE_MAX_ROUNDS)
        ),
    )


# Backward-compatible singleton (legacy callers). Prefer create_ai_debate_orchestrator().
ai_debate_orchestrator = AIDebateOrchestrator(
    consensus_threshold=settings.DEBATE_CONSENSUS_THRESHOLD,
    max_rounds=settings.DEBATE_MAX_ROUNDS,
)
