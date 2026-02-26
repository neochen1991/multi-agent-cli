"""
Debate flow entrypoint.

This module keeps backward-compatible symbols while delegating execution
to the LangGraph runtime orchestrator implementation.
"""

from app.config import settings
from app.runtime.langgraph_runtime import (
    LangGraphRuntimeOrchestrator,
    DebateTurn,
)

# Backward-compatible aliases
DebateRound = DebateTurn
AIDebateOrchestrator = LangGraphRuntimeOrchestrator
LangGraphDebateOrchestrator = LangGraphRuntimeOrchestrator


ai_debate_orchestrator = AIDebateOrchestrator(
    consensus_threshold=settings.DEBATE_CONSENSUS_THRESHOLD,
    max_rounds=settings.DEBATE_MAX_ROUNDS,
)
