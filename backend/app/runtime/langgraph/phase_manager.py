"""Phase manager for orchestrator lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PhaseManager:
    """Simple phase transitions for RCA workflow."""

    def phase_for_round(self, current_round: int, max_rounds: int) -> str:
        if current_round <= 0:
            return "coordination"
        if current_round >= max_rounds:
            return "judgment"
        return "analysis"

    def summarize(self, *, current_round: int, max_rounds: int) -> Dict[str, int | str]:
        return {
            "current_round": current_round,
            "max_rounds": max_rounds,
            "phase": self.phase_for_round(current_round, max_rounds),
        }

