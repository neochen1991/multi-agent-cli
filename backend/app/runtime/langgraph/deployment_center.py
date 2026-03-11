"""Deployment profile center for graph topology selection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings


@dataclass(frozen=True)
class DeploymentProfile:
    """封装DeploymentProfile相关数据结构或服务能力。"""
    name: str
    description: str
    analysis_agents: List[str]
    collaboration_enabled: bool
    critique_enabled: bool
    require_verification_plan: bool
    governance_mode: str
    skill_mode: str

    def to_dict(self) -> Dict[str, Any]:
        """执行todict相关逻辑，并为当前模块提供可复用的处理能力。"""
        return {
            "name": self.name,
            "description": self.description,
            "analysis_agents": list(self.analysis_agents),
            "collaboration_enabled": self.collaboration_enabled,
            "critique_enabled": self.critique_enabled,
            "require_verification_plan": self.require_verification_plan,
            "governance_mode": self.governance_mode,
            "skill_mode": self.skill_mode,
        }


class DeploymentCenter:
    """封装DeploymentCenter相关数据结构或服务能力。"""
    def __init__(self) -> None:
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        core_agents = ["LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent"]
        balanced_agents = core_agents + ["MetricsAgent"]
        full_agents = balanced_agents + ["ChangeAgent", "RunbookAgent", "RuleSuggestionAgent"]
        self._profiles: Dict[str, DeploymentProfile] = {
            "baseline": DeploymentProfile(
                name="baseline",
                description="基础图拓扑，仅保留核心分析链路",
                analysis_agents=core_agents,
                collaboration_enabled=False,
                critique_enabled=False,
                require_verification_plan=False,
                governance_mode="none",
                skill_mode="minimal",
            ),
            "skill_enabled": DeploymentProfile(
                name="skill_enabled",
                description="启用技能增强的常规分析拓扑",
                analysis_agents=balanced_agents,
                collaboration_enabled=False,
                critique_enabled=False,
                require_verification_plan=True,
                governance_mode="standard",
                skill_mode="enabled",
            ),
            "investigation_full": DeploymentProfile(
                name="investigation_full",
                description="完整调查拓扑，启用协作与批判环节",
                analysis_agents=full_agents,
                collaboration_enabled=True,
                critique_enabled=True,
                require_verification_plan=True,
                governance_mode="standard",
                skill_mode="enabled",
            ),
            "production_governed": DeploymentProfile(
                name="production_governed",
                description="生产治理拓扑，为审批与门禁场景预留扩展",
                analysis_agents=full_agents,
                collaboration_enabled=True,
                critique_enabled=True,
                require_verification_plan=True,
                governance_mode="approval_ready",
                skill_mode="enabled",
            ),
        }
        self._file = Path(settings.LOCAL_STORE_DIR) / "deployment_profile.json"
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> List[Dict[str, Any]]:
        """负责列出profiles，并返回后续流程可直接消费的数据结果。"""
        return [row.to_dict() for row in self._profiles.values()]

    def get_profile(self, name: str) -> Dict[str, Any]:
        """负责获取配置档，并返回后续流程可直接消费的数据结果。"""
        key = str(name or "").strip()
        profile = self._profiles.get(key) or self._profiles["skill_enabled"]
        return profile.to_dict()

    def get_active(self) -> Dict[str, Any]:
        """负责获取激活，并返回后续流程可直接消费的数据结果。"""
        if not self._file.exists():
            return {"active_profile": "skill_enabled", "updated_at": ""}
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            return {"active_profile": "skill_enabled", "updated_at": ""}
        if not isinstance(payload, dict):
            return {"active_profile": "skill_enabled", "updated_at": ""}
        return {
            "active_profile": str(payload.get("active_profile") or "skill_enabled"),
            "updated_at": str(payload.get("updated_at") or ""),
        }

    def set_active(self, profile_name: str) -> Dict[str, Any]:
        """执行set激活相关逻辑，并为当前模块提供可复用的处理能力。"""
        profile = str(profile_name or "").strip()
        if profile not in self._profiles:
            profile = "skill_enabled"
        payload = {
            "active_profile": profile,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def select(
        self,
        *,
        severity: str,
        execution_mode: str,
        requested_profile: str = "",
    ) -> Dict[str, Any]:
        """执行选择，用于驱动当前阶段的策略选择或状态流转。"""
        requested = str(requested_profile or "").strip()
        if requested in self._profiles:
            return self.get_profile(requested)

        manual = self.get_active()
        active_profile = str(manual.get("active_profile") or "skill_enabled")
        if active_profile and active_profile != "skill_enabled":
            return self.get_profile(active_profile)

        severity_text = str(severity or "").strip().lower()
        mode_text = str(execution_mode or "").strip().lower()
        if mode_text == "quick":
            return self.get_profile("baseline")
        if severity_text in {"critical", "p0"}:
            return self.get_profile("production_governed")
        return self.get_profile("skill_enabled")


deployment_center = DeploymentCenter()


__all__ = ["deployment_center", "DeploymentCenter", "DeploymentProfile"]
