"""OpenRCA-style skill template and scenario parameter injector."""

from __future__ import annotations

from typing import Any, Dict


RCA_SKILL_TEMPLATE: Dict[str, Any] = {
    "name": "open_rca_diagnosis",
    "version": "1.0",
    "phases": ["context_intake", "evidence_collection", "cross_validation", "judgment", "verification"],
    "rules": [
        "结论必须可追溯到证据，避免无依据推断",
        "根因必须包含日志或指标证据 + 代码或领域证据（跨源约束）",
        "优先输出可执行的下一步验证计划",
    ],
    "forbidden": [
        "禁止仅复述上下文，不产出结论",
        "禁止输出“需要进一步分析”且不给出下一步",
        "禁止跳过主Agent命令直接执行无关任务",
    ],
    "output_contract": {
        "chat_message": "1-3句会议口吻发言",
        "analysis": "结构化分析摘要",
        "conclusion": "明确结论",
        "confidence": "0-1",
        "evidence_chain": "引用证据链（含来源）",
    },
}


def build_rca_skill_context(*, context: Dict[str, Any], loop_round: int, max_rounds: int) -> Dict[str, Any]:
    """构建构建rcaSkill上下文，供后续节点或调用方直接使用。"""
    incident = context.get("incident") if isinstance(context.get("incident"), dict) else {}
    interface_mapping = context.get("interface_mapping") if isinstance(context.get("interface_mapping"), dict) else {}
    debate_cfg = context.get("debate_config") if isinstance(context.get("debate_config"), dict) else {}
    scenario = {
        "incident_id": str(incident.get("id") or ""),
        "severity": str(incident.get("severity") or ""),
        "service_name": str(incident.get("service_name") or ""),
        "target_interface": str((interface_mapping.get("matched_endpoint") or {}).get("interface") or ""),
        "owner_team": str(interface_mapping.get("responsible_team") or ""),
        "loop_round": int(loop_round),
        "max_rounds": int(max_rounds),
        "debate_mode": str(debate_cfg.get("mode") or "standard"),
    }
    return {
        "skill": RCA_SKILL_TEMPLATE,
        "scenario": scenario,
    }


__all__ = ["RCA_SKILL_TEMPLATE", "build_rca_skill_context"]
