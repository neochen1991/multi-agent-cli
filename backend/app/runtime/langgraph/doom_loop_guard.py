"""Detect and break repetitive routing loops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class DoomLoopGuard:
    """Guardrail for supervisor repeated-step loops."""

    threshold: int = 3
    forced_step: str = "speak:JudgeAgent"

    def should_force(self, next_step: str, recent_steps: List[str]) -> bool:
        target = str(next_step or "").strip()
        if not target or target in {"speak:JudgeAgent", "JudgeAgent", "judge"}:
            return False
        window = [str(item or "").strip() for item in recent_steps[-self.threshold :]]
        if len(window) < self.threshold:
            return False
        return all(item == target for item in window)

