"""Runtime strategy center for DoomLoop/Compaction/Prune/Truncation/PhaseManager."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings


@dataclass(frozen=True)
class StrategyProfile:
    name: str
    description: str
    suggested_max_rounds: int
    doom_loop_max_repeat: int
    compaction_max_messages: int
    prune_history_limit: int
    truncation_max_chars: int
    phase_mode: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "suggested_max_rounds": self.suggested_max_rounds,
            "doom_loop_max_repeat": self.doom_loop_max_repeat,
            "compaction_max_messages": self.compaction_max_messages,
            "prune_history_limit": self.prune_history_limit,
            "truncation_max_chars": self.truncation_max_chars,
            "phase_mode": self.phase_mode,
        }


class RuntimeStrategyCenter:
    def __init__(self) -> None:
        self._profiles: Dict[str, StrategyProfile] = {
            "balanced": StrategyProfile(
                name="balanced",
                description="默认均衡策略，兼顾质量与时延",
                suggested_max_rounds=1,
                doom_loop_max_repeat=2,
                compaction_max_messages=12,
                prune_history_limit=20,
                truncation_max_chars=1800,
                phase_mode="standard",
            ),
            "high_concurrency": StrategyProfile(
                name="high_concurrency",
                description="高并发优先，缩短上下文并快速收敛",
                suggested_max_rounds=1,
                doom_loop_max_repeat=1,
                compaction_max_messages=8,
                prune_history_limit=12,
                truncation_max_chars=1200,
                phase_mode="fast_track",
            ),
            "timeout_sensitive": StrategyProfile(
                name="timeout_sensitive",
                description="超时敏感场景，减少回合并加强降级保护",
                suggested_max_rounds=1,
                doom_loop_max_repeat=1,
                compaction_max_messages=7,
                prune_history_limit=10,
                truncation_max_chars=1000,
                phase_mode="failfast",
            ),
            "low_cost": StrategyProfile(
                name="low_cost",
                description="低成本策略，压缩 token 并减少工具扩展",
                suggested_max_rounds=1,
                doom_loop_max_repeat=1,
                compaction_max_messages=6,
                prune_history_limit=8,
                truncation_max_chars=900,
                phase_mode="economy",
            ),
        }
        self._file = Path(settings.LOCAL_STORE_DIR) / "runtime_strategy.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> List[Dict[str, Any]]:
        return [row.to_dict() for row in self._profiles.values()]

    def get_profile(self, name: str) -> Dict[str, Any]:
        profile = self._profiles.get(str(name or "").strip())
        if not profile:
            profile = self._profiles["balanced"]
        return profile.to_dict()

    def get_active(self) -> Dict[str, Any]:
        if not self._file.exists():
            return {"active_profile": "balanced", "updated_at": ""}
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            return {"active_profile": "balanced", "updated_at": ""}
        if not isinstance(payload, dict):
            return {"active_profile": "balanced", "updated_at": ""}
        return {
            "active_profile": str(payload.get("active_profile") or "balanced"),
            "updated_at": str(payload.get("updated_at") or ""),
        }

    def set_active(self, profile_name: str) -> Dict[str, Any]:
        profile = str(profile_name or "").strip()
        if profile not in self._profiles:
            profile = "balanced"
        payload = {
            "active_profile": profile,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def select(self, *, severity: str, execution_mode: str) -> Dict[str, Any]:
        severity_text = str(severity or "").strip().lower()
        mode_text = str(execution_mode or "").strip().lower()
        manual = self.get_active()
        active_profile = str(manual.get("active_profile") or "balanced")
        if active_profile and active_profile != "balanced":
            return self.get_profile(active_profile)
        if mode_text in {"background", "async"}:
            return self.get_profile("high_concurrency")
        if severity_text in {"critical", "p0"}:
            return self.get_profile("timeout_sensitive")
        if mode_text == "quick":
            return self.get_profile("low_cost")
        return self.get_profile("balanced")


runtime_strategy_center = RuntimeStrategyCenter()


__all__ = ["runtime_strategy_center", "RuntimeStrategyCenter", "StrategyProfile"]
