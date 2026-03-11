"""Cross-agent focused context assembler."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_cross_agent_focused_context(
    service: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    tool_context: Optional[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    leads = service._extract_investigation_leads(compact_context, incident_context, assigned_command)  # noqa: SLF001
    payload = {
        "problem_frame": {
            "title": str(((compact_context.get("incident_summary") or {}).get("title") or incident_context.get("title") or ""))[:200],
            "description": str(((compact_context.get("incident_summary") or {}).get("description") or incident_context.get("description") or ""))[:600],
            "service_name": service._primary_service_name(compact_context, incident_context, assigned_command),  # noqa: SLF001
            "severity": str(((compact_context.get("incident_summary") or {}).get("severity") or incident_context.get("severity") or ""))[:40],
        },
        "investigation_focus": {
            "api_endpoints": list(leads.get("api_endpoints") or [])[:8],
            "service_names": list(leads.get("service_names") or [])[:8],
            "database_tables": service._extract_database_tables(compact_context, incident_context, assigned_command)[:12],  # noqa: SLF001
            "error_keywords": list(leads.get("error_keywords") or [])[:10],
            "trace_ids": list(leads.get("trace_ids") or [])[:6],
        },
        "tool_summary": {
            "name": str((tool_context or {}).get("name") or ""),
            "status": str((tool_context or {}).get("status") or ""),
            "summary": str((tool_context or {}).get("summary") or "")[:320],
        },
    }
    role_hint = str((assigned_command or {}).get("target_role") or "").strip().lower()
    task_text = " ".join(
        filter(
            None,
            [str((assigned_command or {}).get("task") or "").strip(), str((assigned_command or {}).get("focus") or "").strip()],
        )
    ).lower()
    if role_hint in {"commander", "main", "problem_analysis"} or "分发" in task_text or "拆解" in task_text:
        payload["coordination_summary"] = build_problem_coordination_summary(
            problem_frame=payload["problem_frame"],
            investigation_focus=payload["investigation_focus"],
            tool_summary=payload["tool_summary"],
        )
    if "裁决" in task_text or "最终判断" in task_text or "收敛证据" in task_text:
        payload["verdict_summary"] = build_judge_verdict_summary(
            problem_frame=payload["problem_frame"],
            investigation_focus=payload["investigation_focus"],
            tool_summary=payload["tool_summary"],
        )
    if "验证" in task_text or "回落" in task_text or "修复是否生效" in task_text:
        payload["verification_summary"] = build_verification_summary(
            problem_frame=payload["problem_frame"],
            investigation_focus=payload["investigation_focus"],
            tool_summary=payload["tool_summary"],
        )
    if "质疑" in task_text or "证据缺口" in task_text or "替代解释" in task_text:
        payload["critique_summary"] = build_critique_summary(
            problem_frame=payload["problem_frame"],
            investigation_focus=payload["investigation_focus"],
            tool_summary=payload["tool_summary"],
        )
    if "反驳" in task_text or "补强" in task_text or "闭环证据" in task_text:
        payload["rebuttal_summary"] = build_rebuttal_summary(
            problem_frame=payload["problem_frame"],
            investigation_focus=payload["investigation_focus"],
            tool_summary=payload["tool_summary"],
        )
    if "规则化建议" in task_text or "守护策略" in task_text or "告警" in task_text:
        payload["rule_summary"] = build_rule_summary(
            problem_frame=payload["problem_frame"],
            investigation_focus=payload["investigation_focus"],
            tool_summary=payload["tool_summary"],
        )
    return payload


def build_problem_coordination_summary(
    *,
    problem_frame: Dict[str, Any],
    investigation_focus: Dict[str, Any],
    tool_summary: Dict[str, Any],
) -> Dict[str, Any]:
    database_tables = list(investigation_focus.get("database_tables") or [])[:12]
    error_keywords = [str(item or "").strip().lower() for item in list(investigation_focus.get("error_keywords") or [])]
    api_endpoints = list(investigation_focus.get("api_endpoints") or [])[:8]

    priority_tracks: List[str] = []
    dispatch_targets: List[str] = []
    evidence_points: List[str] = []
    dominant_pattern = "generic_investigation"

    if api_endpoints:
        priority_tracks.append("接口入口与故障表象确认")
        dispatch_targets.extend(["LogAgent", "CodeAgent"])
        evidence_points.append(f"问题接口：{api_endpoints[0]}")
    if database_tables or any(token in " ".join(error_keywords) for token in ("db", "lock", "transaction", "pool")):
        priority_tracks.append("数据库与连接池压力链")
        dispatch_targets.append("DatabaseAgent")
        evidence_points.append(f"数据库线索：{';'.join(database_tables[:3]) or 'db/pool/lock keyword'}")
    if any(token in " ".join(error_keywords) for token in ("502", "timeout", "error")):
        priority_tracks.append("日志时间线与用户可见故障闭环")
        dispatch_targets.append("LogAgent")
        evidence_points.append("错误关键词显示用户侧故障已暴露，需要先重建时间线。")
    if tool_summary.get("status"):
        evidence_points.append(f"主控预加载：{str(tool_summary.get('name') or '-')}/{str(tool_summary.get('status') or '-')}")

    if len(priority_tracks) >= 2:
        dominant_pattern = "multi_signal_incident"
    if not dispatch_targets:
        dispatch_targets = ["LogAgent", "DomainAgent", "CodeAgent"]

    return {
        "dominant_pattern": dominant_pattern,
        "service_name": str(problem_frame.get("service_name") or "")[:160],
        "priority_tracks": list(dict.fromkeys(priority_tracks))[:4],
        "dispatch_targets": list(dict.fromkeys(dispatch_targets))[:5],
        "evidence_points": list(dict.fromkeys(evidence_points))[:6],
    }


def build_judge_verdict_summary(
    *,
    problem_frame: Dict[str, Any],
    investigation_focus: Dict[str, Any],
    tool_summary: Dict[str, Any],
) -> Dict[str, Any]:
    api_endpoints = list(investigation_focus.get("api_endpoints") or [])[:8]
    database_tables = list(investigation_focus.get("database_tables") or [])[:12]
    error_keywords = [str(item or "").strip().lower() for item in list(investigation_focus.get("error_keywords") or [])]

    decision_axes: List[str] = []
    evidence_points: List[str] = []
    dominant_pattern = "needs_more_evidence"

    if api_endpoints:
        decision_axes.append("接口级故障是否可与日志和代码入口闭环")
        evidence_points.append(f"问题接口：{api_endpoints[0]}")
    if database_tables:
        decision_axes.append("数据库线索是否足以支撑根因归属")
        evidence_points.append(f"关键表：{';'.join(database_tables[:3])}")
    if any(token in " ".join(error_keywords) for token in ("502", "timeout", "lock", "db")):
        decision_axes.append("用户故障表象与底层资源争用是否一致")
        evidence_points.append(f"错误线索：{';'.join(error_keywords[:4])}")
    if tool_summary.get("status"):
        evidence_points.append(f"裁决输入：{str(tool_summary.get('name') or '-')}/{str(tool_summary.get('status') or '-')}")

    if len(decision_axes) >= 2:
        dominant_pattern = "ready_for_verdict"

    return {
        "dominant_pattern": dominant_pattern,
        "service_name": str(problem_frame.get("service_name") or "")[:160],
        "decision_axes": list(dict.fromkeys(decision_axes))[:4],
        "evidence_points": list(dict.fromkeys(evidence_points))[:6],
    }


def build_verification_summary(
    *,
    problem_frame: Dict[str, Any],
    investigation_focus: Dict[str, Any],
    tool_summary: Dict[str, Any],
) -> Dict[str, Any]:
    api_endpoints = list(investigation_focus.get("api_endpoints") or [])[:8]
    database_tables = list(investigation_focus.get("database_tables") or [])[:12]
    error_keywords = [str(item or "").strip().lower() for item in list(investigation_focus.get("error_keywords") or [])]

    checkpoints: List[str] = []
    evidence_points: List[str] = []
    dominant_pattern = "verification_generic"

    if api_endpoints:
        checkpoints.append("确认接口错误率和超时率回落")
        evidence_points.append(f"验证对象：{api_endpoints[0]}")
    if database_tables or any(token in " ".join(error_keywords) for token in ("db", "lock", "pool")):
        checkpoints.append("确认数据库连接池、锁等待和慢 SQL 指标回落")
        evidence_points.append(f"数据面线索：{';'.join(database_tables[:3]) or 'db/lock/pool keyword'}")
    checkpoints.append("确认关键服务 CPU/线程等资源指标恢复")
    if tool_summary.get("status"):
        evidence_points.append(f"验证输入：{str(tool_summary.get('name') or '-')}/{str(tool_summary.get('status') or '-')}")
    if len(checkpoints) >= 2:
        dominant_pattern = "verification_ready"

    return {
        "dominant_pattern": dominant_pattern,
        "service_name": str(problem_frame.get("service_name") or "")[:160],
        "checkpoints": list(dict.fromkeys(checkpoints))[:5],
        "evidence_points": list(dict.fromkeys(evidence_points))[:6],
    }


def build_critique_summary(
    *,
    problem_frame: Dict[str, Any],
    investigation_focus: Dict[str, Any],
    tool_summary: Dict[str, Any],
) -> Dict[str, Any]:
    api_endpoints = list(investigation_focus.get("api_endpoints") or [])[:8]
    database_tables = list(investigation_focus.get("database_tables") or [])[:12]
    error_keywords = [str(item or "").strip().lower() for item in list(investigation_focus.get("error_keywords") or [])]
    challenge_axes: List[str] = []
    evidence_points: List[str] = []
    dominant_pattern = "generic_challenge"
    if api_endpoints:
        challenge_axes.append("接口现象是否存在其他解释路径")
        evidence_points.append(f"问题接口：{api_endpoints[0]}")
    if database_tables:
        challenge_axes.append("数据库线索是否足以证明唯一根因")
        evidence_points.append(f"涉及表：{';'.join(database_tables[:3])}")
    if error_keywords:
        challenge_axes.append("错误关键词是否可能来自级联症状而非根因")
        evidence_points.append(f"现有线索：{';'.join(error_keywords[:4])}")
    if tool_summary.get("status"):
        evidence_points.append(f"质疑输入：{str(tool_summary.get('name') or '-')}/{str(tool_summary.get('status') or '-')}")
    if len(challenge_axes) >= 2:
        dominant_pattern = "evidence_challenge"
    return {
        "dominant_pattern": dominant_pattern,
        "service_name": str(problem_frame.get("service_name") or "")[:160],
        "challenge_axes": list(dict.fromkeys(challenge_axes))[:4],
        "evidence_points": list(dict.fromkeys(evidence_points))[:6],
    }


def build_rebuttal_summary(
    *,
    problem_frame: Dict[str, Any],
    investigation_focus: Dict[str, Any],
    tool_summary: Dict[str, Any],
) -> Dict[str, Any]:
    api_endpoints = list(investigation_focus.get("api_endpoints") or [])[:8]
    database_tables = list(investigation_focus.get("database_tables") or [])[:12]
    error_keywords = [str(item or "").strip().lower() for item in list(investigation_focus.get("error_keywords") or [])]
    reinforcement_axes: List[str] = []
    evidence_points: List[str] = []
    dominant_pattern = "generic_rebuttal"
    if api_endpoints:
        reinforcement_axes.append("补强接口入口到用户故障的闭环")
        evidence_points.append(f"问题接口：{api_endpoints[0]}")
    if database_tables or any(token in " ".join(error_keywords) for token in ("lock", "db", "pool")):
        reinforcement_axes.append("补强数据库/资源争用证据链")
        evidence_points.append(f"数据面：{';'.join(database_tables[:3]) or 'db/lock/pool keyword'}")
    if tool_summary.get("status"):
        evidence_points.append(f"反驳输入：{str(tool_summary.get('name') or '-')}/{str(tool_summary.get('status') or '-')}")
    if len(reinforcement_axes) >= 2:
        dominant_pattern = "evidence_reinforcement"
    return {
        "dominant_pattern": dominant_pattern,
        "service_name": str(problem_frame.get("service_name") or "")[:160],
        "reinforcement_axes": list(dict.fromkeys(reinforcement_axes))[:4],
        "evidence_points": list(dict.fromkeys(evidence_points))[:6],
    }


def build_rule_summary(
    *,
    problem_frame: Dict[str, Any],
    investigation_focus: Dict[str, Any],
    tool_summary: Dict[str, Any],
) -> Dict[str, Any]:
    api_endpoints = list(investigation_focus.get("api_endpoints") or [])[:8]
    database_tables = list(investigation_focus.get("database_tables") or [])[:12]
    error_keywords = [str(item or "").strip().lower() for item in list(investigation_focus.get("error_keywords") or [])]
    recommendation_axes: List[str] = []
    evidence_points: List[str] = []
    dominant_pattern = "generic_rule"
    if api_endpoints:
        recommendation_axes.append("沉淀接口级告警与守护规则")
        evidence_points.append(f"问题接口：{api_endpoints[0]}")
    if database_tables or any(token in " ".join(error_keywords) for token in ("pool", "db", "timeout")):
        recommendation_axes.append("沉淀数据库/连接池容量守护策略")
        evidence_points.append(f"数据面：{';'.join(database_tables[:3]) or 'db/pool keyword'}")
    if tool_summary.get("status"):
        evidence_points.append(f"规则输入：{str(tool_summary.get('name') or '-')}/{str(tool_summary.get('status') or '-')}")
    if len(recommendation_axes) >= 2:
        dominant_pattern = "rule_ready"
    return {
        "dominant_pattern": dominant_pattern,
        "service_name": str(problem_frame.get("service_name") or "")[:160],
        "recommendation_axes": list(dict.fromkeys(recommendation_axes))[:4],
        "evidence_points": list(dict.fromkeys(evidence_points))[:6],
    }
