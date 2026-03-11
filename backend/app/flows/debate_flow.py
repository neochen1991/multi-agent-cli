"""
Debate flow entrypoint.

This module keeps backward-compatible symbols while delegating execution
to the LangGraph runtime orchestrator implementation.
"""

from typing import Optional

from app.config import settings
from app.runtime_core import (
    LangGraphRuntimeOrchestrator,
    DebateTurn,
)
from app.runtime.langgraph_runtime import (
    normalize_analysis_depth_mode,
    resolve_analysis_depth_max_rounds,
)

# Backward-compatible aliases
DebateRound = DebateTurn
AIDebateOrchestrator = LangGraphRuntimeOrchestrator
LangGraphDebateOrchestrator = LangGraphRuntimeOrchestrator


def create_ai_debate_orchestrator(
    *,
    max_rounds: Optional[int] = None,
    consensus_threshold: Optional[float] = None,
    analysis_depth_mode: Optional[str] = None,
) -> LangGraphRuntimeOrchestrator:
    """Create a new orchestrator instance per request to avoid shared mutable state."""
    # 每次请求都创建独立 orchestrator，避免共享实例把深度模式和轮次配置串到别的会话。
    return AIDebateOrchestrator(
        consensus_threshold=(
            float(consensus_threshold)
            if consensus_threshold is not None
            else float(settings.DEBATE_CONSENSUS_THRESHOLD)
        ),
        max_rounds=(int(max_rounds) if max_rounds is not None else None),
        analysis_depth_mode=normalize_analysis_depth_mode(analysis_depth_mode),
    )


# Backward-compatible singleton (legacy callers). Prefer create_ai_debate_orchestrator().
ai_debate_orchestrator = AIDebateOrchestrator(
    consensus_threshold=settings.DEBATE_CONSENSUS_THRESHOLD,
    max_rounds=None,
    analysis_depth_mode=settings.DEBATE_ANALYSIS_DEPTH_MODE,
)
