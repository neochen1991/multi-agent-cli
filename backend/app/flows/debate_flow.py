"""
Debate flow entrypoint.

This module keeps backward-compatible symbols while delegating execution
to the AutoGen Runtime orchestrator implementation.
"""

from app.config import settings
from app.runtime.autogen_runtime import (
    AutoGenRuntimeOrchestrator,
    DebateTurn,
)

# Backward-compatible alias
DebateRound = DebateTurn
AIDebateOrchestrator = AutoGenRuntimeOrchestrator


ai_debate_orchestrator = AIDebateOrchestrator(
    consensus_threshold=settings.DEBATE_CONSENSUS_THRESHOLD,
    max_rounds=settings.DEBATE_MAX_ROUNDS,
)
