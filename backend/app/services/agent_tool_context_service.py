"""
按 Agent 角色构建外部工具上下文。

这个服务负责把“主 Agent 的命令”转换成真正可执行的工具上下文：
- 先做 command gate 决策
- 再按 Agent 类型选择具体工具
- 最后输出统一结构和审计日志
"""

from __future__ import annotations

import asyncio
import csv
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit

import structlog
try:
    import asyncpg
except Exception:  # pragma: no cover - optional dependency
    asyncpg = None  # type: ignore[assignment]

from app.config import settings
from app.models.tooling import AgentToolingConfig
from app.runtime.connectors import (
    APMConnector,
    AlertPlatformConnector,
    CMDBConnector,
    GrafanaConnector,
    LogCloudConnector,
    LokiConnector,
    PrometheusConnector,
    TelemetryConnector,
)
from app.services.tooling_service import tooling_service
from app.services.agent_skill_service import agent_skill_service
from app.services.knowledge_service import knowledge_service
from app.tools.case_library import CaseLibraryTool

logger = structlog.get_logger()


SOURCE_SUFFIXES = {
    ".py",
    ".java",
    ".kt",
    ".go",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rs",
    ".sql",
    ".yaml",
    ".yml",
    ".json",
    ".xml",
    ".properties",
    ".md",
}

GIT_FETCH_TIMEOUTS = (15, 25)
GIT_CLONE_TIMEOUTS = (30, 45)
GIT_LOCAL_TIMEOUT = 20


@dataclass
class ToolContextResult:
    """统一的工具上下文返回结构，供 runtime、前端和审计链复用。"""
    name: str
    enabled: bool
    used: bool
    status: str
    summary: str
    data: Dict[str, Any]
    command_gate: Dict[str, Any] = field(default_factory=dict)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    execution_path: str = ""
    permission_decision: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转成普通字典，便于直接塞进运行时上下文。"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "used": self.used,
            "status": self.status,
            "summary": self.summary,
            "data": self.data,
            "command_gate": self.command_gate,
            "audit_log": self.audit_log,
            "execution_path": self.execution_path,
            "permission_decision": self.permission_decision,
        }


class AgentToolContextService:
    """封装AgentToolContextService相关数据结构或服务能力。"""
    def __init__(self) -> None:
        """初始化本地工具、远端连接器和审计计数器。"""
        self._case_library = CaseLibraryTool()
        self._telemetry_connector = TelemetryConnector()
        self._cmdb_connector = CMDBConnector()
        self._prometheus_connector = PrometheusConnector()
        self._loki_connector = LokiConnector()
        self._grafana_connector = GrafanaConnector()
        self._apm_connector = APMConnector()
        self._logcloud_connector = LogCloudConnector()
        self._alert_platform_connector = AlertPlatformConnector()
        self._audit_seq = 0

    async def build_context(
        self,
        *,
        agent_name: str,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建某个 Agent 当前轮次可用的工具上下文。

        这是服务主入口，负责：
        1. 根据命令判断是否允许调用工具。
        2. 根据 Agent 角色路由到对应 `_build_*_context`。
        3. 把 skill 注入和工具审计并入同一份结果。
        """
        command_gate = self._decide_tool_invocation(agent_name=agent_name, assigned_command=assigned_command)
        cfg = await tooling_service.get_config()
        # 这里的分支不是简单按名字分发，而是在定义“每类 Agent 允许看什么证据源”。
        # 这样主 Agent 只需要下发方向，具体的工具接入边界由系统统一控制。
        if agent_name == "CodeAgent":
            result = await self._build_code_context(
                cfg, compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "ProblemAnalysisAgent":
            # 主Agent默认使用“规则建议工具包”聚合指标与案例库证据
            result = await self._build_rule_suggestion_context(
                cfg,
                compact_context,
                incident_context,
                assigned_command,
                command_gate,
            )
        elif agent_name == "ChangeAgent":
            result = await self._build_change_context(
                cfg, compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "LogAgent":
            result = await self._build_log_context(
                cfg, compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "MetricsAgent":
            result = await self._build_metrics_context(
                cfg,
                compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "RunbookAgent":
            result = await self._build_runbook_context(
                compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "CriticAgent":
            # 质疑Agent基于客观指标做反证与漏洞审查
            result = await self._build_metrics_context(
                cfg,
                compact_context,
                incident_context,
                assigned_command,
                command_gate,
            )
        elif agent_name == "RebuttalAgent":
            # 反驳Agent优先补充日志侧证据
            result = await self._build_log_context(
                cfg,
                compact_context,
                incident_context,
                assigned_command,
                command_gate,
            )
        elif agent_name == "JudgeAgent":
            # 裁决Agent基于规则建议工具包汇总可验证证据
            result = await self._build_rule_suggestion_context(
                cfg,
                compact_context,
                incident_context,
                assigned_command,
                command_gate,
            )
        elif agent_name == "VerificationAgent":
            # 验证Agent基于指标快照生成验证与回归观察点
            result = await self._build_metrics_context(
                cfg,
                compact_context,
                incident_context,
                assigned_command,
                command_gate,
            )
        elif agent_name == "RuleSuggestionAgent":
            result = await self._build_rule_suggestion_context(
                cfg,
                compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "DomainAgent":
            result = await self._build_domain_context(
                cfg, compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "DatabaseAgent":
            result = await self._build_database_context(
                cfg, compact_context, incident_context, assigned_command, command_gate
            )
        else:
            result = ToolContextResult(
                name="none",
                enabled=False,
                used=False,
                status="skipped",
                summary="当前 Agent 无外部工具配置。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    self._audit(
                        tool_name="none",
                        action="tool_skip",
                        status="skipped",
                        detail={"reason": "当前 Agent 无外部工具配置。"},
                    )
                ],
            )
        result = self._merge_skill_context(
            result=result,
            cfg=cfg,
            agent_name=agent_name,
            compact_context=compact_context,
            incident_context=incident_context,
            assigned_command=assigned_command,
        )
        # 无论实际是否命中工具，最终都会把标准化 investigation leads 带回去，
        # 让 Agent 在工具不可用时仍可基于已有线索完成受限分析。
        result.data = {
            **dict(result.data or {}),
            "investigation_leads": self._extract_investigation_leads(
                compact_context,
                incident_context,
                assigned_command,
            ),
        }
        result.permission_decision = {
            "allow_tool": bool(command_gate.get("allow_tool")),
            "reason": str(command_gate.get("reason") or ""),
            "decision_source": str(command_gate.get("decision_source") or ""),
        }
        if not result.execution_path:
            if result.name in {"telemetry_connector", "cmdb_connector"}:
                result.execution_path = "remote"
            elif result.name in {
                "git_repo_search",
                "git_change_window",
                "local_log_reader",
                "domain_excel_lookup",
                "db_snapshot_reader",
            }:
                result.execution_path = "local"
            else:
                result.execution_path = "none"
        return result.to_dict()

    def build_focused_context(
        self,
        *,
        agent_name: str,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]] = None,
        assigned_command: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """为指定 Agent 生成更贴近问题闭包的专属上下文。"""
        if agent_name == "CodeAgent":
            return self._build_code_focused_context(compact_context, incident_context, tool_context, assigned_command)
        if agent_name == "LogAgent":
            return self._build_log_focused_context(compact_context, incident_context, tool_context, assigned_command)
        if agent_name == "DomainAgent":
            return self._build_domain_focused_context(compact_context, incident_context, tool_context, assigned_command)
        if agent_name == "DatabaseAgent":
            return self._build_database_focused_context(compact_context, incident_context, tool_context, assigned_command)
        if agent_name == "MetricsAgent":
            return self._build_metrics_focused_context(compact_context, incident_context, tool_context, assigned_command)
        if agent_name == "ChangeAgent":
            return self._build_change_focused_context(compact_context, incident_context, tool_context, assigned_command)
        if agent_name == "RunbookAgent":
            return self._build_runbook_focused_context(compact_context, incident_context, tool_context, assigned_command)
        if agent_name in {"ProblemAnalysisAgent", "CriticAgent", "RebuttalAgent", "JudgeAgent", "VerificationAgent", "RuleSuggestionAgent"}:
            return self._build_cross_agent_focused_context(compact_context, incident_context, tool_context, assigned_command)
        return {}

    def _merge_skill_context(
        self,
        *,
        result: ToolContextResult,
        cfg: AgentToolingConfig,
        agent_name: str,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
    ) -> ToolContextResult:
        """把 skill 命中结果并入已有工具上下文，形成统一的注入视图。"""
        gate = dict(result.command_gate or {})
        if not bool(gate.get("has_command")):
            return result
        if bool(gate.get("has_command")) and not bool(gate.get("allow_tool")):
            return result

        skill_result = agent_skill_service.select_skills(
            agent_name=agent_name,
            cfg=cfg.skills,
            assigned_command=assigned_command,
            compact_context=compact_context,
            incident_context=incident_context,
        )
        if not bool(skill_result.get("enabled")):
            return result
        if not bool(skill_result.get("used")):
            return result

        skill_payload = {
            "status": str(skill_result.get("status") or ""),
            "summary": str(skill_result.get("summary") or ""),
            "items": list(skill_result.get("skills") or []),
        }
        combined_data = dict(result.data or {})
        combined_data["skill_context"] = skill_payload

        normalized_skill_audit: List[Dict[str, Any]] = []
        for entry in list(skill_result.get("audit_log") or []):
            if not isinstance(entry, dict):
                continue
            normalized_skill_audit.append(
                self._audit(
                    tool_name="agent_skill_router",
                    action=str(entry.get("action") or "skill_call"),
                    status=str(entry.get("status") or "ok"),
                    detail=dict(entry.get("detail") or {}),
                )
            )

        if result.name in {"none", ""}:
            return ToolContextResult(
                name="agent_skill_router",
                enabled=True,
                used=True,
                status="ok",
                summary=str(skill_result.get("summary") or "Skill 调用成功。"),
                data=combined_data,
                command_gate=dict(result.command_gate or {}),
                audit_log=[*list(result.audit_log or []), *normalized_skill_audit],
                execution_path="local",
                permission_decision=dict(result.permission_decision or {}),
            )

        if not bool(result.used):
            base_snapshot = {
                "name": result.name,
                "enabled": bool(result.enabled),
                "used": bool(result.used),
                "status": str(result.status or ""),
                "summary": str(result.summary or ""),
            }
            combined_data["base_tool_context"] = base_snapshot
            return ToolContextResult(
                name="agent_skill_router",
                enabled=True,
                used=True,
                status="ok",
                summary=(
                    f"{str(skill_result.get('summary') or '').strip()}；"
                    f"原工具状态={base_snapshot['status'] or 'unknown'}"
                ).strip("；"),
                data=combined_data,
                command_gate=dict(result.command_gate or {}),
                audit_log=[*list(result.audit_log or []), *normalized_skill_audit],
                execution_path="local",
                permission_decision=dict(result.permission_decision or {}),
            )

        result.data = combined_data
        result.summary = f"{result.summary}；{str(skill_result.get('summary') or '').strip()}".strip("；")
        result.audit_log = [*list(result.audit_log or []), *normalized_skill_audit]
        if not result.execution_path:
            result.execution_path = "local"
        return result

    def _build_cross_agent_focused_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        leads = self._extract_investigation_leads(compact_context, incident_context, assigned_command)
        payload = {
            "problem_frame": {
                "title": str(((compact_context.get("incident_summary") or {}).get("title") or incident_context.get("title") or ""))[:200],
                "description": str(((compact_context.get("incident_summary") or {}).get("description") or incident_context.get("description") or ""))[:600],
                "service_name": self._primary_service_name(compact_context, incident_context, assigned_command),
                "severity": str(((compact_context.get("incident_summary") or {}).get("severity") or incident_context.get("severity") or ""))[:40],
            },
            "investigation_focus": {
                "api_endpoints": list(leads.get("api_endpoints") or [])[:8],
                "service_names": list(leads.get("service_names") or [])[:8],
                "database_tables": self._extract_database_tables(compact_context, incident_context, assigned_command)[:12],
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
                [
                    str((assigned_command or {}).get("task") or "").strip(),
                    str((assigned_command or {}).get("focus") or "").strip(),
                ],
            )
        ).lower()
        if role_hint in {"commander", "main", "problem_analysis"} or "分发" in task_text or "拆解" in task_text:
            payload["coordination_summary"] = self._build_problem_coordination_summary(
                problem_frame=payload["problem_frame"],
                investigation_focus=payload["investigation_focus"],
                tool_summary=payload["tool_summary"],
            )
        if "裁决" in task_text or "最终判断" in task_text or "收敛证据" in task_text:
            payload["verdict_summary"] = self._build_judge_verdict_summary(
                problem_frame=payload["problem_frame"],
                investigation_focus=payload["investigation_focus"],
                tool_summary=payload["tool_summary"],
            )
        if "验证" in task_text or "回落" in task_text or "修复是否生效" in task_text:
            payload["verification_summary"] = self._build_verification_summary(
                problem_frame=payload["problem_frame"],
                investigation_focus=payload["investigation_focus"],
                tool_summary=payload["tool_summary"],
            )
        if "质疑" in task_text or "证据缺口" in task_text or "替代解释" in task_text:
            payload["critique_summary"] = self._build_critique_summary(
                problem_frame=payload["problem_frame"],
                investigation_focus=payload["investigation_focus"],
                tool_summary=payload["tool_summary"],
            )
        if "反驳" in task_text or "补强" in task_text or "闭环证据" in task_text:
            payload["rebuttal_summary"] = self._build_rebuttal_summary(
                problem_frame=payload["problem_frame"],
                investigation_focus=payload["investigation_focus"],
                tool_summary=payload["tool_summary"],
            )
        if "规则化建议" in task_text or "守护策略" in task_text or "告警" in task_text:
            payload["rule_summary"] = self._build_rule_summary(
                problem_frame=payload["problem_frame"],
                investigation_focus=payload["investigation_focus"],
                tool_summary=payload["tool_summary"],
            )
        return payload

    def _build_problem_coordination_summary(
        self,
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

    def _build_judge_verdict_summary(
        self,
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

    def _build_verification_summary(
        self,
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

    def _build_critique_summary(
        self,
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

    def _build_rebuttal_summary(
        self,
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

    def _build_rule_summary(
        self,
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

    def _build_code_focused_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        mapping = compact_context.get("interface_mapping") if isinstance(compact_context.get("interface_mapping"), dict) else {}
        endpoint = ((mapping.get("endpoint") or mapping.get("matched_endpoint") or {}) if isinstance(mapping, dict) else {})
        leads = self._extract_investigation_leads(compact_context, incident_context, assigned_command)
        tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
        if not isinstance(tool_data, dict):
            tool_data = {}
        hits = [item for item in list(tool_data.get("hits") or []) if isinstance(item, dict)]
        repo_path = str(tool_data.get("repo_path") or "").strip()
        artifact_hints = list(mapping.get("code_artifacts") or []) + list(leads.get("code_artifacts") or [])
        hit_files = [str(item.get("file") or "").strip() for item in hits if str(item.get("file") or "").strip()]
        related_files = self._expand_related_code_files(
            repo_path=repo_path,
            seed_files=[*artifact_hints, *hit_files],
            class_hints=list(leads.get("class_names") or []),
            depth=2,
            per_hop_limit=6,
        )
        code_windows = self._load_repo_focus_windows(
            repo_path=repo_path,
            candidate_files=[*artifact_hints, *hit_files, *related_files],
            max_files=8,
            max_chars=1400,
        )
        method_call_chain = self._build_method_call_chain(
            repo_path=repo_path,
            endpoint_interface=str(endpoint.get("interface") or ""),
            code_windows=code_windows,
            hit_snippets=[str(item.get("snippet") or "") for item in hits[:8]],
        )
        return {
            "analysis_objective": {
                "task": str((assigned_command or {}).get("task") or "")[:240],
                "focus": str((assigned_command or {}).get("focus") or "")[:300],
                "expected_output": str((assigned_command or {}).get("expected_output") or "")[:240],
            },
            "problem_entrypoint": {
                "method": str(endpoint.get("method") or "")[:24],
                "path": str(endpoint.get("path") or "")[:240],
                "service": str(endpoint.get("service") or self._primary_service_name(compact_context, incident_context, assigned_command))[:160],
                "interface": str(endpoint.get("interface") or "")[:240],
            },
            "mapped_code_scope": {
                "code_artifacts": list(dict.fromkeys([str(item) for item in artifact_hints if str(item).strip()]))[:12],
                "class_names": list(leads.get("class_names") or [])[:12],
                "dependency_services": list(leads.get("dependency_services") or [])[:10],
                "database_tables": self._extract_database_tables(compact_context, incident_context, assigned_command)[:12],
            },
            "repo_hits": {
                "keywords": list(tool_data.get("keywords") or [])[:12],
                "match_count": len(hits),
                "top_hits": hits[:12],
                "candidate_files": list(dict.fromkeys([str(item) for item in hit_files if str(item).strip()]))[:12],
                "related_files": related_files[:12],
            },
            "code_windows": code_windows,
            "method_call_chain": method_call_chain,
            "analysis_expectations": [
                "优先定位接口入口与事务边界，再分析同步调用、锁竞争、连接占用和重试放大。",
                "若无法形成完整调用链，至少给出入口方法、下游调用点和可疑资源占用点。",
            ],
        }

    def _build_log_focused_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        excerpt = self._resolve_log_excerpt(compact_context, incident_context, tool_context)
        timeline = self._extract_log_timeline(excerpt, max_events=10)
        trace_id = self._primary_trace_id(compact_context, incident_context, assigned_command)
        causal_timeline = self._build_log_causal_timeline(timeline)
        return {
            "analysis_objective": {
                "task": str((assigned_command or {}).get("task") or "")[:240],
                "focus": str((assigned_command or {}).get("focus") or "")[:300],
            },
            "log_scope": {
                "service_name": self._primary_service_name(compact_context, incident_context, assigned_command),
                "trace_id": trace_id,
                "keywords": list(((tool_context or {}).get("data") or {}).get("keywords") or [])[:10] if isinstance(tool_context, dict) else [],
            },
            "timeline_events": timeline,
            "causal_timeline": causal_timeline,
            "raw_excerpt": excerpt[:2200],
        }

    def _build_domain_focused_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        mapping = compact_context.get("interface_mapping") if isinstance(compact_context.get("interface_mapping"), dict) else {}
        tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
        if not isinstance(tool_data, dict):
            tool_data = {}
        matches = [item for item in list(tool_data.get("matches") or []) if isinstance(item, dict)]
        endpoint = ((mapping.get("endpoint") or mapping.get("matched_endpoint") or {}) if isinstance(mapping, dict) else {})
        causal_summary = self._build_domain_causal_summary(
            mapping=mapping if isinstance(mapping, dict) else {},
            endpoint=endpoint if isinstance(endpoint, dict) else {},
            matches=matches[:8],
        )
        return {
            "responsibility_mapping": {
                "matched": bool(mapping.get("matched")),
                "confidence": mapping.get("confidence"),
                "domain": str(mapping.get("domain") or "")[:120],
                "aggregate": str(mapping.get("aggregate") or "")[:120],
                "owner_team": str(mapping.get("owner_team") or "")[:120],
                "owner": str(mapping.get("owner") or "")[:120],
                "feature": str(mapping.get("feature") or "")[:120],
            },
            "interface_scope": {
                "method": str(endpoint.get("method") or "")[:24],
                "path": str(endpoint.get("path") or "")[:240],
                "service": str(endpoint.get("service") or self._primary_service_name(compact_context, incident_context, assigned_command))[:160],
                "database_tables": list(mapping.get("database_tables") or mapping.get("db_tables") or [])[:12],
                "dependency_services": list(mapping.get("dependency_services") or [])[:10],
                "monitor_items": list(mapping.get("monitor_items") or [])[:10],
            },
            "knowledge_matches": matches[:8],
            "cmdb_payload": (((tool_data.get("remote_cmdb") or {}).get("payload") or {}) if isinstance(tool_data.get("remote_cmdb"), dict) else {}),
            "causal_summary": causal_summary,
        }

    def _build_database_focused_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
        if not isinstance(tool_data, dict):
            tool_data = {}
        target_tables = self._extract_database_tables(compact_context, incident_context, assigned_command)[:16]
        causal_summary = self._build_database_causal_summary(
            target_tables=target_tables,
            tool_data=tool_data,
        )
        return {
            "analysis_objective": {
                "task": str((assigned_command or {}).get("task") or "")[:240],
                "focus": str((assigned_command or {}).get("focus") or "")[:300],
            },
            "target_tables": target_tables,
            "schema_summary": {
                "engine": str(tool_data.get("engine") or "")[:40],
                "schema": str(tool_data.get("schema") or "")[:80],
                "tables": list(tool_data.get("tables") or [])[:16],
                "table_structures": list(tool_data.get("table_structures") or [])[:8],
                "indexes": self._trim_mapping(tool_data.get("indexes"), item_limit=8, value_limit=6),
            },
            "sql_signals": {
                "slow_sql": list(tool_data.get("slow_sql") or [])[:8],
                "top_sql": list(tool_data.get("top_sql") or [])[:8],
                "keyword_hits": list(tool_data.get("keyword_hits") or [])[:8],
            },
            "runtime_signals": {
                "session_status": list(tool_data.get("session_status") or [])[:8],
                "used_target_tables": bool(tool_data.get("used_target_tables")),
                "fallback_reason": str(tool_data.get("fallback_reason") or "")[:120],
            },
            "causal_summary": causal_summary,
        }

    def _build_metrics_focused_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
        if not isinstance(tool_data, dict):
            tool_data = {}
        signals = [item for item in list(tool_data.get("signals") or []) if isinstance(item, dict)]
        causal_metric_chain = self._build_metric_causal_chain(signals[:16])
        return {
            "analysis_objective": {
                "task": str((assigned_command or {}).get("task") or "")[:240],
                "focus": str((assigned_command or {}).get("focus") or "")[:300],
            },
            "metric_signals": signals[:16],
            "metric_timeline_summary": self._summarize_metric_signals(signals[:16]),
            "causal_metric_chain": causal_metric_chain,
            "remote_sources": {
                "telemetry": self._remote_source_summary(tool_data.get("remote_telemetry")),
                "prometheus": self._remote_source_summary(tool_data.get("remote_prometheus")),
                "loki": self._remote_source_summary(tool_data.get("remote_loki")),
                "grafana": self._remote_source_summary(tool_data.get("remote_grafana")),
                "apm": self._remote_source_summary(tool_data.get("remote_apm")),
            },
        }

    def _build_change_focused_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
        if not isinstance(tool_data, dict):
            tool_data = {}
        leads = self._extract_investigation_leads(compact_context, incident_context, assigned_command)
        changes = [item for item in list(tool_data.get("changes") or []) if isinstance(item, dict)]
        causal_summary = self._build_change_causal_summary(
            compact_context=compact_context,
            incident_context=incident_context,
            assigned_command=assigned_command,
            changes=changes,
        )
        return {
            "analysis_objective": {
                "task": str((assigned_command or {}).get("task") or "")[:240],
                "focus": str((assigned_command or {}).get("focus") or "")[:300],
            },
            "service_scope": {
                "service_name": self._primary_service_name(compact_context, incident_context, assigned_command),
                "api_endpoints": list(leads.get("api_endpoints") or [])[:8],
                "code_artifacts": list(leads.get("code_artifacts") or [])[:10],
            },
            "change_window": changes[:12],
            "causal_summary": causal_summary,
        }

    def _build_runbook_focused_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
        if not isinstance(tool_data, dict):
            tool_data = {}
        items = [item for item in list(tool_data.get("items") or []) if isinstance(item, dict)]
        recommended_actions = self._extract_runbook_actions(items[:6])
        action_summary = self._build_runbook_action_summary(
            compact_context=compact_context,
            incident_context=incident_context,
            assigned_command=assigned_command,
            items=items[:6],
            recommended_actions=recommended_actions,
            source=str(tool_data.get("source") or "")[:80],
        )
        return {
            "analysis_objective": {
                "task": str((assigned_command or {}).get("task") or "")[:240],
                "focus": str((assigned_command or {}).get("focus") or "")[:300],
            },
            "knowledge_source": str(tool_data.get("source") or "")[:80],
            "matched_entries": items[:6],
            "recommended_actions": recommended_actions,
            "action_summary": action_summary,
        }

    async def _build_code_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        """构建构建代码上下文，供后续节点或调用方直接使用。"""
        tool_cfg = cfg.code_repo
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="git_repo_search",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not tool_cfg.enabled:
            return ToolContextResult(
                name="git_repo_search",
                enabled=False,
                used=False,
                status="disabled",
                summary="CodeAgent Git 工具开关已关闭，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="git_repo_search",
                        action="config_check",
                        status="disabled",
                        detail={"enabled": False},
                    ),
                ],
            )
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="git_repo_search",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 CodeAgent 调用 Git 工具：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )

        try:
            repo_path = await asyncio.to_thread(
                self._resolve_repo_path,
                tool_cfg.repo_url,
                tool_cfg.access_token,
                tool_cfg.branch,
                tool_cfg.local_repo_path,
                audit_log,
            )
            if not repo_path:
                return ToolContextResult(
                    name="git_repo_search",
                    enabled=True,
                    used=False,
                    status="unavailable",
                    summary="未配置可用仓库地址/本地路径，使用默认分析逻辑。",
                    data={},
                    command_gate=command_gate,
                    audit_log=audit_log,
                )
            keywords = self._extract_keywords(compact_context, incident_context, assigned_command)
            hits, scan_meta = await asyncio.to_thread(
                self._search_repo,
                repo_path,
                keywords,
                int(tool_cfg.max_hits),
            )
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="repo_search",
                    status="ok",
                    detail=scan_meta,
                )
            )
            summary = f"仓库检索完成，命中 {len(hits)} 条代码片段。"
            return ToolContextResult(
                name="git_repo_search",
                enabled=True,
                used=True,
                status="ok",
                summary=summary,
                data={
                    "repo_path": str(repo_path),
                    "keywords": keywords,
                    "hits": hits[: int(tool_cfg.max_hits)],
                },
                command_gate=command_gate,
                audit_log=audit_log,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            logger.warning("code_tool_context_failed", error=error_text)
            return ToolContextResult(
                name="git_repo_search",
                enabled=True,
                used=False,
                status="error",
                summary=f"Git 工具调用失败：{error_text}，已回退默认分析逻辑。",
                data={"error": error_text},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="git_repo_search",
                        action="tool_execute",
                        status="error",
                        detail={"error": error_text},
                    ),
                ],
            )

    async def _build_log_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        """构建构建日志上下文，供后续节点或调用方直接使用。"""
        tool_cfg = cfg.log_file
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="local_log_reader",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not tool_cfg.enabled:
            return ToolContextResult(
                name="local_log_reader",
                enabled=False,
                used=False,
                status="disabled",
                summary="LogAgent 日志文件工具开关已关闭，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="local_log_reader",
                        action="config_check",
                        status="disabled",
                        detail={"enabled": False},
                    ),
                ],
            )
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="local_log_reader",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 LogAgent 读取日志：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        path = Path(str(tool_cfg.file_path or "").strip())
        if not path.exists() or not path.is_file():
            return ToolContextResult(
                name="local_log_reader",
                enabled=True,
                used=False,
                status="unavailable",
                summary="日志文件路径不可用，已回退默认分析逻辑。",
                data={"file_path": str(path)},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="local_log_reader",
                        action="file_check",
                        status="unavailable",
                        detail={"file_path": str(path)},
                    ),
                ],
            )
        try:
            keywords = self._extract_keywords(compact_context, incident_context, assigned_command)
            service_name = self._primary_service_name(compact_context, incident_context, assigned_command)
            trace_id = self._primary_trace_id(compact_context, incident_context, assigned_command)
            remote_logcloud_payload: Dict[str, Any] = {}
            if bool(getattr(cfg, "logcloud_source", None) and cfg.logcloud_source.enabled):
                logcloud_result = await self._logcloud_connector.fetch(
                    cfg.logcloud_source,
                    {
                        "service_name": service_name,
                        "trace_id": trace_id,
                        "query": " ".join(keywords[:6]),
                    },
                )
                logcloud_status = str(logcloud_result.get("status") or "unknown")
                logcloud_request_meta = dict(logcloud_result.get("request_meta") or {})
                audit_log.append(
                    self._audit(
                        tool_name="logcloud_connector",
                        action="remote_fetch",
                        status=logcloud_status,
                        detail={
                            "enabled": bool(cfg.logcloud_source.enabled),
                            "endpoint": str(cfg.logcloud_source.endpoint or "")[:180],
                            "message": str(logcloud_result.get("message") or "")[:180],
                            "request_meta": logcloud_request_meta,
                        },
                    )
                )
                if logcloud_status == "ok" and isinstance(logcloud_result.get("data"), dict):
                    remote_logcloud_payload = dict(logcloud_result.get("data") or {})
            excerpt, line_count, read_meta = await asyncio.to_thread(
                self._read_log_excerpt,
                path,
                int(tool_cfg.max_lines),
                keywords,
            )
            audit_log.append(
                self._audit(
                    tool_name="local_log_reader",
                    action="file_read",
                    status="ok",
                    detail=read_meta,
                )
            )
            return ToolContextResult(
                name="local_log_reader",
                enabled=True,
                used=True,
                status="ok",
                summary=f"日志文件读取完成，采样 {line_count} 行。",
                data={
                    "file_path": str(path),
                    "line_count": line_count,
                    "keywords": keywords,
                    "excerpt": excerpt,
                    "remote_logcloud": {
                        "enabled": bool(getattr(cfg, "logcloud_source", None) and cfg.logcloud_source.enabled),
                        "status": "ok" if remote_logcloud_payload else "disabled_or_unavailable",
                        "payload": remote_logcloud_payload,
                    },
                },
                command_gate=command_gate,
                audit_log=audit_log,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            logger.warning("log_tool_context_failed", error=error_text)
            return ToolContextResult(
                name="local_log_reader",
                enabled=True,
                used=False,
                status="error",
                summary=f"日志文件读取失败：{error_text}，已回退默认分析逻辑。",
                data={"error": error_text},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="local_log_reader",
                        action="file_read",
                        status="error",
                        detail={"error": error_text, "file_path": str(path)},
                    ),
                ],
            )

    async def _build_domain_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        """构建构建domain上下文，供后续节点或调用方直接使用。"""
        tool_cfg = cfg.domain_excel
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="domain_excel_lookup",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not tool_cfg.enabled:
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=False,
                used=False,
                status="disabled",
                summary="DomainAgent 责任田 Excel 工具开关已关闭，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="domain_excel_lookup",
                        action="config_check",
                        status="disabled",
                        detail={"enabled": False},
                    ),
                ],
            )
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 DomainAgent 查询责任田文档：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        path = Path(str(tool_cfg.excel_path or "").strip())
        if not path.exists() or not path.is_file():
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=True,
                used=False,
                status="unavailable",
                summary="责任田 Excel 路径不可用，已回退默认分析逻辑。",
                data={"excel_path": str(path)},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="domain_excel_lookup",
                        action="file_check",
                        status="unavailable",
                        detail={"excel_path": str(path)},
                    ),
                ],
            )
        try:
            keywords = self._extract_keywords(compact_context, incident_context, assigned_command)
            service_name = self._primary_service_name(compact_context, incident_context, assigned_command)
            result = await asyncio.to_thread(
                self._lookup_domain_file,
                path,
                str(tool_cfg.sheet_name or "").strip(),
                int(tool_cfg.max_rows),
                int(tool_cfg.max_matches),
                keywords,
            )
            cmdb_payload: Dict[str, Any] = {}
            if bool(cfg.cmdb_source.enabled):
                cmdb_result = await self._cmdb_connector.fetch(
                    cfg.cmdb_source,
                    {
                        "service_name": service_name,
                        "keywords": keywords[:8],
                    },
                )
                cmdb_status = str(cmdb_result.get("status") or "unknown")
                cmdb_request_meta = dict(cmdb_result.get("request_meta") or {})
                audit_log.append(
                    self._audit(
                        tool_name="cmdb_connector",
                        action="remote_fetch",
                        status=cmdb_status,
                        detail={
                            "enabled": bool(cfg.cmdb_source.enabled),
                            "endpoint": str(cfg.cmdb_source.endpoint or "")[:180],
                            "message": str(cmdb_result.get("message") or "")[:180],
                            "request_meta": cmdb_request_meta,
                        },
                    )
                )
                if cmdb_status == "ok" and isinstance(cmdb_result.get("data"), dict):
                    cmdb_payload = dict(cmdb_result.get("data") or {})
            audit_log.append(
                self._audit(
                    tool_name="domain_excel_lookup",
                    action="file_read",
                    status="ok",
                    detail={
                        "excel_path": str(path),
                        "row_count": int(result.get("row_count") or 0),
                        "match_count": len(list(result.get("matches") or [])),
                        "sheet_used": str(result.get("sheet_used") or ""),
                        "format": str(result.get("format") or ""),
                    },
                )
            )
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=True,
                used=True,
                status="ok",
                summary=f"责任田文档查询完成，命中 {len(result.get('matches') or [])} 行。",
                data={
                    "excel_path": str(path),
                    "keywords": keywords,
                    **result,
                    "remote_cmdb": {
                        "enabled": bool(cfg.cmdb_source.enabled),
                        "status": "ok" if cmdb_payload else "disabled_or_unavailable",
                        "payload": cmdb_payload,
                    },
                },
                command_gate=command_gate,
                audit_log=audit_log,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            logger.warning("domain_tool_context_failed", error=error_text)
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=True,
                used=False,
                status="error",
                summary=f"责任田文档查询失败：{error_text}，已回退默认分析逻辑。",
                data={"error": error_text},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="domain_excel_lookup",
                        action="file_read",
                        status="error",
                        detail={"error": error_text, "excel_path": str(path)},
                    ),
                ],
            )

    async def _build_metrics_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        """构建构建metrics上下文，供后续节点或调用方直接使用。"""
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="metrics_snapshot_analyzer",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="metrics_snapshot_analyzer",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 MetricsAgent 分析指标：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        remote_telemetry_payload: Dict[str, Any] = {}
        remote_prometheus_payload: Dict[str, Any] = {}
        remote_loki_payload: Dict[str, Any] = {}
        remote_grafana_payload: Dict[str, Any] = {}
        remote_apm_payload: Dict[str, Any] = {}
        service_name = self._primary_service_name(compact_context, incident_context, assigned_command)
        trace_id = self._primary_trace_id(compact_context, incident_context, assigned_command)
        if bool(cfg.telemetry_source.enabled):
            telemetry_result = await self._telemetry_connector.fetch(
                cfg.telemetry_source,
                {
                    "service_name": service_name,
                    "trace_id": trace_id,
                },
            )
            telemetry_status = str(telemetry_result.get("status") or "unknown")
            telemetry_request_meta = dict(telemetry_result.get("request_meta") or {})
            audit_log.append(
                self._audit(
                    tool_name="telemetry_connector",
                    action="remote_fetch",
                    status=telemetry_status,
                    detail={
                        "enabled": bool(cfg.telemetry_source.enabled),
                        "endpoint": str(cfg.telemetry_source.endpoint or "")[:180],
                        "message": str(telemetry_result.get("message") or "")[:180],
                        "request_meta": telemetry_request_meta,
                    },
                )
            )
            if telemetry_status == "ok" and isinstance(telemetry_result.get("data"), dict):
                remote_telemetry_payload = dict(telemetry_result.get("data") or {})
        if bool(getattr(cfg, "prometheus_source", None) and cfg.prometheus_source.enabled):
            prometheus_result = await self._prometheus_connector.fetch(
                cfg.prometheus_source,
                {
                    "service_name": service_name,
                    "query": str(assigned_command.get("focus") if isinstance(assigned_command, dict) else ""),
                },
            )
            prometheus_status = str(prometheus_result.get("status") or "unknown")
            prometheus_request_meta = dict(prometheus_result.get("request_meta") or {})
            audit_log.append(
                self._audit(
                    tool_name="prometheus_connector",
                    action="remote_fetch",
                    status=prometheus_status,
                    detail={
                        "enabled": bool(cfg.prometheus_source.enabled),
                        "endpoint": str(cfg.prometheus_source.endpoint or "")[:180],
                        "message": str(prometheus_result.get("message") or "")[:180],
                        "request_meta": prometheus_request_meta,
                    },
                )
            )
            if prometheus_status == "ok" and isinstance(prometheus_result.get("data"), dict):
                remote_prometheus_payload = dict(prometheus_result.get("data") or {})
        if bool(getattr(cfg, "loki_source", None) and cfg.loki_source.enabled):
            loki_result = await self._loki_connector.fetch(
                cfg.loki_source,
                {
                    "service_name": service_name,
                    "trace_id": trace_id,
                    "query": str(assigned_command.get("focus") if isinstance(assigned_command, dict) else ""),
                },
            )
            loki_status = str(loki_result.get("status") or "unknown")
            loki_request_meta = dict(loki_result.get("request_meta") or {})
            audit_log.append(
                self._audit(
                    tool_name="loki_connector",
                    action="remote_fetch",
                    status=loki_status,
                    detail={
                        "enabled": bool(cfg.loki_source.enabled),
                        "endpoint": str(cfg.loki_source.endpoint or "")[:180],
                        "message": str(loki_result.get("message") or "")[:180],
                        "request_meta": loki_request_meta,
                    },
                )
            )
            if loki_status == "ok" and isinstance(loki_result.get("data"), dict):
                remote_loki_payload = dict(loki_result.get("data") or {})
        if bool(getattr(cfg, "grafana_source", None) and cfg.grafana_source.enabled):
            grafana_result = await self._grafana_connector.fetch(
                cfg.grafana_source,
                {
                    "service_name": service_name,
                    "query": str(assigned_command.get("focus") if isinstance(assigned_command, dict) else ""),
                },
            )
            grafana_status = str(grafana_result.get("status") or "unknown")
            grafana_request_meta = dict(grafana_result.get("request_meta") or {})
            audit_log.append(
                self._audit(
                    tool_name="grafana_connector",
                    action="remote_fetch",
                    status=grafana_status,
                    detail={
                        "enabled": bool(cfg.grafana_source.enabled),
                        "endpoint": str(cfg.grafana_source.endpoint or "")[:180],
                        "message": str(grafana_result.get("message") or "")[:180],
                        "request_meta": grafana_request_meta,
                    },
                )
            )
            if grafana_status == "ok" and isinstance(grafana_result.get("data"), dict):
                remote_grafana_payload = dict(grafana_result.get("data") or {})
        if bool(getattr(cfg, "apm_source", None) and cfg.apm_source.enabled):
            apm_result = await self._apm_connector.fetch(
                cfg.apm_source,
                {
                    "service_name": service_name,
                    "trace_id": trace_id,
                    "query": str(assigned_command.get("focus") if isinstance(assigned_command, dict) else ""),
                },
            )
            apm_status = str(apm_result.get("status") or "unknown")
            apm_request_meta = dict(apm_result.get("request_meta") or {})
            audit_log.append(
                self._audit(
                    tool_name="apm_connector",
                    action="remote_fetch",
                    status=apm_status,
                    detail={
                        "enabled": bool(cfg.apm_source.enabled),
                        "endpoint": str(cfg.apm_source.endpoint or "")[:180],
                        "message": str(apm_result.get("message") or "")[:180],
                        "request_meta": apm_request_meta,
                    },
                )
            )
            if apm_status == "ok" and isinstance(apm_result.get("data"), dict):
                remote_apm_payload = dict(apm_result.get("data") or {})
        metrics_context = dict(incident_context or {})
        if remote_telemetry_payload:
            metrics_context["remote_telemetry_payload"] = remote_telemetry_payload
        if remote_prometheus_payload:
            metrics_context["remote_prometheus_payload"] = remote_prometheus_payload
        if remote_loki_payload:
            metrics_context["remote_loki_payload"] = remote_loki_payload
        if remote_grafana_payload:
            metrics_context["remote_grafana_payload"] = remote_grafana_payload
        if remote_apm_payload:
            metrics_context["remote_apm_payload"] = remote_apm_payload
        signals = self._collect_metrics_signals(compact_context, metrics_context)
        audit_log.append(
            self._audit(
                tool_name="metrics_snapshot_analyzer",
                action="metrics_extract",
                status="ok" if signals else "unavailable",
                detail={
                    "signal_count": len(signals),
                    "sources": ["compact_context", "incident_context", "log_content"],
                },
            )
        )
        if not signals:
            return ToolContextResult(
                name="metrics_snapshot_analyzer",
                enabled=True,
                used=False,
                status="unavailable",
                summary="未发现可解析的监控指标快照，使用默认分析逻辑。",
                data={
                    "remote_telemetry": {
                        "enabled": bool(cfg.telemetry_source.enabled),
                        "status": "ok" if remote_telemetry_payload else "disabled_or_unavailable",
                    },
                    "remote_prometheus": {
                        "enabled": bool(getattr(cfg, "prometheus_source", None) and cfg.prometheus_source.enabled),
                        "status": "ok" if remote_prometheus_payload else "disabled_or_unavailable",
                    },
                    "remote_loki": {
                        "enabled": bool(getattr(cfg, "loki_source", None) and cfg.loki_source.enabled),
                        "status": "ok" if remote_loki_payload else "disabled_or_unavailable",
                    },
                    "remote_grafana": {
                        "enabled": bool(getattr(cfg, "grafana_source", None) and cfg.grafana_source.enabled),
                        "status": "ok" if remote_grafana_payload else "disabled_or_unavailable",
                    },
                    "remote_apm": {
                        "enabled": bool(getattr(cfg, "apm_source", None) and cfg.apm_source.enabled),
                        "status": "ok" if remote_apm_payload else "disabled_or_unavailable",
                    },
                },
                command_gate=command_gate,
                audit_log=audit_log,
            )
        return ToolContextResult(
            name="metrics_snapshot_analyzer",
            enabled=True,
            used=True,
            status="ok",
            summary=f"提取到 {len(signals)} 条监控异常信号。",
            data={
                "signals": signals[:20],
                "remote_telemetry": {
                    "enabled": bool(cfg.telemetry_source.enabled),
                    "status": "ok" if remote_telemetry_payload else "disabled_or_unavailable",
                    "payload": remote_telemetry_payload,
                },
                "remote_prometheus": {
                    "enabled": bool(getattr(cfg, "prometheus_source", None) and cfg.prometheus_source.enabled),
                    "status": "ok" if remote_prometheus_payload else "disabled_or_unavailable",
                    "payload": remote_prometheus_payload,
                },
                "remote_loki": {
                    "enabled": bool(getattr(cfg, "loki_source", None) and cfg.loki_source.enabled),
                    "status": "ok" if remote_loki_payload else "disabled_or_unavailable",
                    "payload": remote_loki_payload,
                },
                "remote_grafana": {
                    "enabled": bool(getattr(cfg, "grafana_source", None) and cfg.grafana_source.enabled),
                    "status": "ok" if remote_grafana_payload else "disabled_or_unavailable",
                    "payload": remote_grafana_payload,
                },
                "remote_apm": {
                    "enabled": bool(getattr(cfg, "apm_source", None) and cfg.apm_source.enabled),
                    "status": "ok" if remote_apm_payload else "disabled_or_unavailable",
                    "payload": remote_apm_payload,
                },
            },
            command_gate=command_gate,
            audit_log=audit_log,
        )

    async def _build_change_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        """构建构建change上下文，供后续节点或调用方直接使用。"""
        tool_cfg = cfg.code_repo
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="git_change_window",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not tool_cfg.enabled:
            return ToolContextResult(
                name="git_change_window",
                enabled=False,
                used=False,
                status="disabled",
                summary="ChangeAgent 变更工具开关已关闭，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="git_change_window",
                        action="config_check",
                        status="disabled",
                        detail={"enabled": False},
                    ),
                ],
            )
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="git_change_window",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 ChangeAgent 拉取变更窗口：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        try:
            repo_path = await asyncio.to_thread(
                self._resolve_repo_path,
                tool_cfg.repo_url,
                tool_cfg.access_token,
                tool_cfg.branch,
                tool_cfg.local_repo_path,
                audit_log,
            )
            if not repo_path:
                return ToolContextResult(
                    name="git_change_window",
                    enabled=True,
                    used=False,
                    status="unavailable",
                    summary="未配置可用仓库地址/本地路径，无法拉取变更窗口。",
                    data={},
                    command_gate=command_gate,
                    audit_log=audit_log,
                )
            changes = await asyncio.to_thread(
                self._collect_recent_git_changes,
                repo_path,
                int(getattr(tool_cfg, "max_hits", 20) or 20),
                audit_log,
            )
            if not changes:
                return ToolContextResult(
                    name="git_change_window",
                    enabled=True,
                    used=False,
                    status="unavailable",
                    summary="未获取到有效变更记录，已回退默认分析逻辑。",
                    data={"repo_path": repo_path, "changes": []},
                    command_gate=command_gate,
                    audit_log=audit_log,
                )
            return ToolContextResult(
                name="git_change_window",
                enabled=True,
                used=True,
                status="ok",
                summary=f"已提取最近 {len(changes)} 条代码变更。",
                data={"repo_path": repo_path, "changes": changes},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            return ToolContextResult(
                name="git_change_window",
                enabled=True,
                used=False,
                status="error",
                summary=f"变更窗口提取失败：{error_text}，已回退默认分析。",
                data={"error": error_text},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="git_change_window",
                        action="tool_execute",
                        status="error",
                        detail={"error": error_text},
                    ),
                ],
            )

    async def _build_database_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        """构建构建database上下文，供后续节点或调用方直接使用。"""
        tool_cfg = getattr(cfg, "database", None)
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="db_snapshot_reader",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not tool_cfg or not bool(getattr(tool_cfg, "enabled", False)):
            return ToolContextResult(
                name="db_snapshot_reader",
                enabled=False,
                used=False,
                status="disabled",
                summary="DatabaseAgent 数据库工具开关已关闭，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="db_snapshot_reader",
                        action="config_check",
                        status="disabled",
                        detail={"enabled": False},
                    ),
                ],
            )
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="db_snapshot_reader",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 DatabaseAgent 调用数据库工具：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        try:
            engine = str(getattr(tool_cfg, "engine", "sqlite") or "sqlite").strip().lower()
            max_rows = int(getattr(tool_cfg, "max_rows", 50) or 50)
            timeout_seconds = int(getattr(tool_cfg, "connect_timeout_seconds", 8) or 8)
            keywords = self._extract_keywords(compact_context, incident_context, assigned_command)
            mapped_tables = self._extract_database_tables(compact_context, incident_context, assigned_command)
            if engine in {"postgresql", "postgres", "pg"}:
                dsn = str(getattr(tool_cfg, "postgres_dsn", "") or "").strip()
                schema = str(getattr(tool_cfg, "pg_schema", "public") or "public").strip() or "public"
                if not dsn:
                    return ToolContextResult(
                        name="db_snapshot_reader",
                        enabled=True,
                        used=False,
                        status="unavailable",
                        summary="PostgreSQL DSN 未配置，已回退默认分析逻辑。",
                        data={"engine": "postgresql"},
                        command_gate=command_gate,
                        audit_log=[
                            *audit_log,
                            self._audit(
                                tool_name="db_snapshot_reader",
                                action="config_check",
                                status="unavailable",
                                detail={"engine": "postgresql", "reason": "postgres_dsn empty"},
                            ),
                        ],
                    )
                if asyncpg is None:
                    return ToolContextResult(
                        name="db_snapshot_reader",
                        enabled=True,
                        used=False,
                        status="error",
                        summary="未安装 asyncpg，无法连接 PostgreSQL，请先安装依赖。",
                        data={"engine": "postgresql", "error": "asyncpg not installed"},
                        command_gate=command_gate,
                        audit_log=[
                            *audit_log,
                            self._audit(
                                tool_name="db_snapshot_reader",
                                action="dependency_check",
                                status="error",
                                detail={"engine": "postgresql", "reason": "asyncpg missing"},
                            ),
                        ],
                    )
                snapshot = await self._collect_postgres_snapshot(
                    dsn=dsn,
                    schema=schema,
                    max_rows=max_rows,
                    keywords=keywords,
                    target_tables=mapped_tables,
                    timeout_seconds=timeout_seconds,
                )
                query_action = "postgres_query"
                query_detail: Dict[str, Any] = {
                    "engine": "postgresql",
                    "schema": schema,
                    "max_rows": max_rows,
                    "requested_tables": mapped_tables[:12],
                    "table_count": int(snapshot.get("table_count") or 0),
                    "slow_sql_count": len(list(snapshot.get("slow_sql") or [])),
                    "top_sql_count": len(list(snapshot.get("top_sql") or [])),
                    "session_count": len(list(snapshot.get("session_status") or [])),
                }
            else:
                db_path = Path(str(getattr(tool_cfg, "db_path", "") or "").strip())
                if not db_path.exists() or not db_path.is_file():
                    return ToolContextResult(
                        name="db_snapshot_reader",
                        enabled=True,
                        used=False,
                        status="unavailable",
                        summary="SQLite 快照文件路径不可用，已回退默认分析逻辑。",
                        data={"engine": "sqlite", "db_path": str(db_path)},
                        command_gate=command_gate,
                        audit_log=[
                            *audit_log,
                            self._audit(
                                tool_name="db_snapshot_reader",
                                action="file_check",
                                status="unavailable",
                                detail={"engine": "sqlite", "db_path": str(db_path)},
                            ),
                        ],
                    )
                snapshot = await asyncio.to_thread(
                    self._collect_database_snapshot,
                    db_path,
                    max_rows,
                    keywords,
                    mapped_tables,
                )
                query_action = "sqlite_query"
                query_detail = {
                    "engine": "sqlite",
                    "db_path": str(db_path),
                    "max_rows": max_rows,
                    "requested_tables": mapped_tables[:12],
                    "table_count": int(snapshot.get("table_count") or 0),
                    "slow_sql_count": len(list(snapshot.get("slow_sql") or [])),
                    "top_sql_count": len(list(snapshot.get("top_sql") or [])),
                    "session_count": len(list(snapshot.get("session_status") or [])),
                }
            audit_log.append(
                self._audit(
                    tool_name="db_snapshot_reader",
                    action=query_action,
                    status="ok",
                    detail=query_detail,
                )
            )
            return ToolContextResult(
                name="db_snapshot_reader",
                enabled=True,
                used=True,
                status="ok",
                summary=(
                    f"数据库快照读取完成，表 {snapshot.get('table_count', 0)} 个，"
                    f"慢SQL {len(list(snapshot.get('slow_sql') or []))} 条。"
                ),
                data=snapshot,
                command_gate=command_gate,
                audit_log=audit_log,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            logger.warning("database_tool_context_failed", error=error_text)
            return ToolContextResult(
                name="db_snapshot_reader",
                enabled=True,
                used=False,
                status="error",
                summary=f"数据库快照读取失败：{error_text}，已回退默认分析逻辑。",
                data={"error": error_text},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="db_snapshot_reader",
                        action="database_query",
                        status="error",
                        detail={"error": error_text},
                    ),
                ],
            )

    async def _build_runbook_context(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        """构建构建runbook上下文，供后续节点或调用方直接使用。"""
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="runbook_case_library",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="runbook_case_library",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 RunbookAgent 检索案例：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        keywords = self._extract_keywords(compact_context, incident_context, assigned_command)
        query = " ".join(keywords[:6]).strip()
        knowledge_items = await knowledge_service.search_reference_entries(
            query=query,
            limit=8,
        )
        audit_log.append(
            self._audit(
                tool_name="runbook_case_library",
                action="knowledge_search",
                status="ok" if knowledge_items else "unavailable",
                detail={"query": query, "match_count": len(knowledge_items), "source": "knowledge_base"},
            )
        )
        if knowledge_items:
            return ToolContextResult(
                name="runbook_case_library",
                enabled=True,
                used=True,
                status="ok",
                summary=f"知识库命中 {len(knowledge_items)} 条案例 / SOP。",
                data={"query": query, "items": knowledge_items[:8], "source": "knowledge_base"},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        result = await self._case_library.execute(action="search", query=query)
        if not result.success:
            error_text = str(result.error or "unknown error")
            return ToolContextResult(
                name="runbook_case_library",
                enabled=True,
                used=False,
                status="error",
                summary=f"案例库查询失败：{error_text}",
                data={"error": error_text, "query": query},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="runbook_case_library",
                        action="case_search",
                        status="error",
                        detail={"error": error_text, "query": query},
                    ),
                ],
            )
        items = []
        payload = result.data if isinstance(result.data, dict) else {}
        raw_items = payload.get("items") if isinstance(payload, dict) else []
        if isinstance(raw_items, list):
            items = [item for item in raw_items if isinstance(item, dict)]
        audit_log.append(
            self._audit(
                tool_name="runbook_case_library",
                action="case_search",
                status="ok",
                detail={"query": query, "match_count": len(items)},
            )
        )
        if not items:
            return ToolContextResult(
                name="runbook_case_library",
                enabled=True,
                used=False,
                status="unavailable",
                summary="案例库无匹配结果，使用默认分析逻辑。",
                data={"query": query},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        return ToolContextResult(
            name="runbook_case_library",
            enabled=True,
            used=True,
            status="ok",
            summary=f"案例库命中 {len(items)} 条相似故障。",
            data={"query": query, "items": items[:8], "source": "legacy_case_library"},
            command_gate=command_gate,
            audit_log=audit_log,
        )

    async def _build_rule_suggestion_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        """构建构建rulesuggestion上下文，供后续节点或调用方直接使用。"""
        metrics = await self._build_metrics_context(
            cfg=cfg,
            compact_context=compact_context,
            incident_context=incident_context,
            assigned_command=assigned_command,
            command_gate=command_gate,
        )
        runbook = await self._build_runbook_context(
            compact_context=compact_context,
            incident_context=incident_context,
            assigned_command=assigned_command,
            command_gate=command_gate,
        )
        alert_payload: Dict[str, Any] = {}
        alert_audit_log: List[Dict[str, Any]] = []
        if bool(getattr(cfg, "alert_platform_source", None) and cfg.alert_platform_source.enabled):
            alert_result = await self._alert_platform_connector.fetch(
                cfg.alert_platform_source,
                {
                    "service_name": str(incident_context.get("service_name") or ""),
                    "severity": str(incident_context.get("severity") or ""),
                    "alert_id": str(incident_context.get("alarm_id") or incident_context.get("alert_id") or ""),
                },
            )
            alert_status = str(alert_result.get("status") or "unknown")
            alert_request_meta = dict(alert_result.get("request_meta") or {})
            alert_audit_log.append(
                self._audit(
                    tool_name="alert_platform_connector",
                    action="remote_fetch",
                    status=alert_status,
                    detail={
                        "enabled": bool(cfg.alert_platform_source.enabled),
                        "endpoint": str(cfg.alert_platform_source.endpoint or "")[:180],
                        "message": str(alert_result.get("message") or "")[:180],
                        "request_meta": alert_request_meta,
                    },
                )
            )
            if alert_status == "ok" and isinstance(alert_result.get("data"), dict):
                alert_payload = dict(alert_result.get("data") or {})
        used = bool(metrics.used or runbook.used)
        status = "ok" if used else ("skipped_by_command" if metrics.status == "skipped_by_command" else "unavailable")
        return ToolContextResult(
            name="rule_suggestion_toolkit",
            enabled=True,
            used=used,
            status=status,
            summary=(
                "已汇总指标与案例库上下文，供规则建议Agent生成阈值与告警窗口。"
                if used
                else "未获得可用的指标/案例上下文，规则建议将基于当前会话推断。"
            ),
            data={
                "metrics_signals": ((metrics.data or {}).get("signals") or [])[:20],
                "runbook_items": ((runbook.data or {}).get("items") or [])[:8],
                "query": (runbook.data or {}).get("query") or "",
                "remote_alert_platform": {
                    "enabled": bool(getattr(cfg, "alert_platform_source", None) and cfg.alert_platform_source.enabled),
                    "status": "ok" if alert_payload else "disabled_or_unavailable",
                    "payload": alert_payload,
                },
            },
            command_gate=command_gate,
            audit_log=[*(metrics.audit_log or []), *(runbook.audit_log or []), *alert_audit_log],
        )

    def _resolve_repo_path(
        self,
        repo_url: str,
        access_token: str,
        branch: str,
        local_repo_path: str,
        audit_log: List[Dict[str, Any]],
    ) -> str:
        """执行resolverepopath相关逻辑，并为当前模块提供可复用的处理能力。"""
        raw_local_path = str(local_repo_path or "").strip()
        local_path = Path(raw_local_path) if raw_local_path else None
        if local_path and local_path.exists() and local_path.is_dir():
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="repo_path_resolve",
                    status="ok",
                    detail={
                        "mode": "local",
                        "local_repo_path": str(local_path),
                    },
                )
            )
            return str(local_path)

        url = str(repo_url or "").strip()
        if not url:
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="repo_path_resolve",
                    status="unavailable",
                    detail={"reason": "repo_url 为空且 local_repo_path 不可用"},
                )
            )
            return ""
        if not self._is_allowed_git_host(url):
            safe_url = self._mask_url_secret(url)
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="permission_check",
                    status="denied",
                    detail={
                        "reason": "repo host not in allowlist",
                        "repo_url": safe_url,
                        "allowlist": list(settings.TOOL_GIT_HOST_ALLOWLIST or []),
                    },
                )
            )
            return ""

        cache_root = Path(settings.LOCAL_STORE_DIR) / "tool_cache" / "repos"
        cache_root.mkdir(parents=True, exist_ok=True)
        repo_key = sha1(url.encode("utf-8")).hexdigest()[:20]
        repo_path = cache_root / repo_key
        auth_url = self._inject_token(url, access_token)
        safe_branch = str(branch or "main").strip() or "main"
        safe_url = self._mask_url_secret(url)
        audit_log.append(
            self._audit(
                tool_name="git_repo_search",
                action="repo_path_resolve",
                status="ok",
                detail={
                    "mode": "remote",
                    "repo_url": safe_url,
                    "branch": safe_branch,
                    "cache_repo_path": str(repo_path),
                },
            )
        )

        if (repo_path / ".git").exists():
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="http_request",
                    status="started",
                    detail={
                        "operation": "git_fetch",
                        "repo_url": safe_url,
                        "branch": safe_branch,
                    },
                )
            )
            try:
                self._run_git_with_retry(
                    ["git", "fetch", "--depth", "1", "origin", safe_branch],
                    cwd=repo_path,
                    audit_log=audit_log,
                    action="git_fetch",
                    repo_url=safe_url,
                    timeout_plan=GIT_FETCH_TIMEOUTS,
                )
                self._run_git(
                    ["git", "checkout", "-B", safe_branch, "FETCH_HEAD"],
                    cwd=repo_path,
                    audit_log=audit_log,
                    action="git_checkout",
                    repo_url="",
                    timeout_seconds=GIT_LOCAL_TIMEOUT,
                )
                self._run_git(
                    ["git", "reset", "--hard", "FETCH_HEAD"],
                    cwd=repo_path,
                    audit_log=audit_log,
                    action="git_reset",
                    repo_url="",
                    timeout_seconds=GIT_LOCAL_TIMEOUT,
                )
            except Exception as exc:
                error_text = str(exc).strip() or exc.__class__.__name__
                audit_log.append(
                    self._audit(
                        tool_name="git_repo_search",
                        action="repo_sync_degraded",
                        status="fallback",
                        detail={
                            "reason": "remote fetch 失败，回退到本地缓存仓库",
                            "repo_path": str(repo_path),
                            "error": error_text[:400],
                        },
                    )
                )
                logger.warning(
                    "git_repo_sync_degraded",
                    repo_path=str(repo_path),
                    repo_url=safe_url,
                    error=error_text[:400],
                )
            return str(repo_path)

        audit_log.append(
            self._audit(
                tool_name="git_repo_search",
                action="http_request",
                status="started",
                detail={
                    "operation": "git_clone",
                    "repo_url": safe_url,
                    "branch": safe_branch,
                },
            )
        )
        if repo_path.exists() and not (repo_path / ".git").exists():
            shutil.rmtree(repo_path, ignore_errors=True)
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="repo_path_cleanup",
                    status="ok",
                    detail={
                        "reason": "清理不完整的历史 clone 目录",
                        "repo_path": str(repo_path),
                    },
                )
            )
        self._run_git_with_retry(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--single-branch",
                "--branch",
                safe_branch,
                auth_url,
                str(repo_path),
            ],
            cwd=cache_root,
            audit_log=audit_log,
            action="git_clone",
            repo_url=safe_url,
            timeout_plan=GIT_CLONE_TIMEOUTS,
        )
        return str(repo_path)

    def _run_git(
        self,
        cmd: List[str],
        cwd: Path,
        *,
        audit_log: List[Dict[str, Any]],
        action: str,
        repo_url: str,
        timeout_seconds: int,
    ) -> None:
        """负责运行git，并处理调用过程中的超时、错误与返回结果。"""
        started = datetime.utcnow()
        safe_cmd = [self._sanitize_command_part(item) for item in cmd]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=max(10, int(timeout_seconds)),
                check=False,
                env=self._git_env(),
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="git_command",
                    status="timeout",
                    detail={
                        "action": action,
                        "cwd": str(cwd),
                        "command": " ".join(safe_cmd),
                        "repo_url": repo_url,
                        "timeout_seconds": int(timeout_seconds),
                        "duration_ms": duration_ms,
                    },
                )
            )
            logger.warning(
                "tool_git_command_timeout",
                action=action,
                cwd=str(cwd),
                command=" ".join(safe_cmd),
                repo_url=repo_url,
                timeout_seconds=int(timeout_seconds),
                duration_ms=duration_ms,
            )
            raise RuntimeError(
                f"git 命令超时({int(timeout_seconds)}s): {' '.join(safe_cmd)}"
            ) from exc

        duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
        detail = {
            "action": action,
            "cwd": str(cwd),
            "command": " ".join(safe_cmd),
            "repo_url": repo_url,
            "return_code": proc.returncode,
            "duration_ms": duration_ms,
            "stdout_preview": str(proc.stdout or "").strip()[:300],
            "stderr_preview": str(proc.stderr or "").strip()[:300],
        }
        audit_log.append(
            self._audit(
                tool_name="git_repo_search",
                action="git_command",
                status="ok" if proc.returncode == 0 else "error",
                detail=detail,
            )
        )
        logger.info(
            "tool_git_command",
            action=action,
            cwd=str(cwd),
            command=" ".join(safe_cmd),
            repo_url=repo_url,
            return_code=proc.returncode,
            duration_ms=duration_ms,
            stdout_preview=str(proc.stdout or "").strip()[:120],
            stderr_preview=str(proc.stderr or "").strip()[:120],
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git command failed")

    def _run_git_with_retry(
        self,
        cmd: List[str],
        *,
        cwd: Path,
        audit_log: List[Dict[str, Any]],
        action: str,
        repo_url: str,
        timeout_plan: tuple[int, ...],
    ) -> None:
        """负责运行gitwithretry，并处理调用过程中的超时、错误与返回结果。"""
        last_error: Optional[Exception] = None
        for index, timeout_seconds in enumerate(timeout_plan, start=1):
            try:
                self._run_git(
                    cmd,
                    cwd=cwd,
                    audit_log=audit_log,
                    action=action,
                    repo_url=repo_url,
                    timeout_seconds=int(timeout_seconds),
                )
                return
            except Exception as exc:
                last_error = exc
                audit_log.append(
                    self._audit(
                        tool_name="git_repo_search",
                        action="git_retry",
                        status="retrying" if index < len(timeout_plan) else "failed",
                        detail={
                            "operation": action,
                            "attempt": index,
                            "max_attempts": len(timeout_plan),
                            "timeout_seconds": int(timeout_seconds),
                            "error": str(exc)[:400],
                        },
                    )
                )
                if index < len(timeout_plan):
                    continue
        raise RuntimeError(str(last_error) if last_error else f"{action} failed")

    def _git_env(self) -> Dict[str, str]:
        """执行gitenv相关逻辑，并为当前模块提供可复用的处理能力。"""
        env = dict(os.environ)
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env.setdefault("GIT_ASKPASS", "echo")
        return env

    def _is_allowed_git_host(self, repo_url: str) -> bool:
        """执行isallowedgithost相关逻辑，并为当前模块提供可复用的处理能力。"""
        raw = str(repo_url or "").strip()
        if not raw:
            return False
        parts = urlsplit(raw)
        host = str(parts.hostname or "").strip().lower()
        if not host:
            return False
        allowlist = [str(item or "").strip().lower() for item in (settings.TOOL_GIT_HOST_ALLOWLIST or []) if str(item or "").strip()]
        if not allowlist:
            return True
        return host in allowlist

    def _inject_token(self, repo_url: str, token: str) -> str:
        """执行injecttoken相关逻辑，并为当前模块提供可复用的处理能力。"""
        raw = str(repo_url or "").strip()
        tk = str(token or "").strip()
        if not tk:
            return raw
        parts = urlsplit(raw)
        if parts.scheme not in {"http", "https"}:
            return raw
        if "@" in parts.netloc:
            return raw
        netloc = f"oauth2:{tk}@{parts.netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def _collect_recent_git_changes(
        self,
        repo_path: str,
        max_items: int,
        audit_log: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """执行收集recentgitchanges相关逻辑，并为当前模块提供可复用的处理能力。"""
        cmd = [
            "git",
            "--no-pager",
            "log",
            f"-n{max(1, min(int(max_items or 20), 80))}",
            "--pretty=format:%H\t%ad\t%an\t%s",
            "--date=iso",
        ]
        try:
            completed = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=GIT_LOCAL_TIMEOUT,
                check=True,
                env=self._git_env(),
            )
            output = completed.stdout or ""
        except subprocess.CalledProcessError as exc:
            err = str(exc.stderr or exc.stdout or "").strip()
            err_lower = err.lower()
            no_commit_markers = (
                "does not have any commits yet",
                "your current branch",
                "no commits yet",
                "bad revision",
            )
            if any(marker in err_lower for marker in no_commit_markers):
                audit_log.append(
                    self._audit(
                        tool_name="git_change_window",
                        action="git_log_changes",
                        status="unavailable",
                        detail={
                            "repo_path": str(repo_path),
                            "reason": "仓库暂无可用提交记录",
                            "stderr": err[:300],
                        },
                    )
                )
                return []
            raise RuntimeError(err or "git log failed") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"git log timeout({GIT_LOCAL_TIMEOUT}s): {str(exc)[:200]}") from exc
        audit_log.append(
            self._audit(
                tool_name="git_change_window",
                action="git_log_changes",
                status="ok",
                detail={"repo_path": str(repo_path), "lines": len(output.splitlines())},
            )
        )
        changes: List[Dict[str, Any]] = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            commit, commit_time, author, subject = parts[0], parts[1], parts[2], parts[3]
            changes.append(
                {
                    "commit": commit[:12],
                    "time": commit_time,
                    "author": author,
                    "subject": subject[:240],
                }
            )
        return changes

    def _collect_metrics_signals(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """执行收集metrics信号相关逻辑，并为当前模块提供可复用的处理能力。"""
        signals: List[Dict[str, Any]] = []
        text_sources = [
            str(compact_context.get("log_excerpt") or ""),
            str(incident_context.get("log_content") or ""),
            str(incident_context.get("description") or ""),
            str(incident_context.get("remote_telemetry_payload") or ""),
            str(incident_context.get("remote_prometheus_payload") or ""),
            str(incident_context.get("remote_loki_payload") or ""),
        ]
        metric_patterns = [
            ("cpu", r"cpu[^0-9]*([0-9]+(?:\.[0-9]+)?%?)", "CPU"),
            ("threads", r"(?:线程|threads?)[^0-9]*([0-9]+)", "线程"),
            ("hikari_pending", r"hikari[^,\n]*pending[^0-9]*([0-9]+)", "Hikari Pending"),
            (
                "db_conn",
                r"(?:db_conn|db\.active\.connections|database\s+connections?)\s*[=:]?\s*([0-9]+/[0-9]+)",
                "DB连接",
            ),
            ("error_rate", r"(?:5xx|error(?:_rate)?)[^0-9]*([0-9]+(?:\.[0-9]+)?%?)", "错误率"),
        ]
        for source_text in text_sources:
            if not source_text:
                continue
            for metric_key, pattern, label in metric_patterns:
                for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
                    value = str(match.group(1) or "").strip()
                    if not value:
                        continue
                    start = max(0, match.start() - 50)
                    end = min(len(source_text), match.end() + 50)
                    snippet = source_text[start:end].strip()
                    signals.append(
                        {
                            "metric": metric_key,
                            "label": label,
                            "value": value,
                            "snippet": snippet[:280],
                        }
                    )
        dedup: List[Dict[str, Any]] = []
        seen = set()
        for item in signals:
            key = f"{item.get('metric')}|{item.get('value')}|{item.get('snippet')}"
            if key in seen:
                continue
            seen.add(key)
            dedup.append(item)
        return dedup[:40]

    async def _collect_postgres_snapshot(
        self,
        *,
        dsn: str,
        schema: str,
        max_rows: int,
        keywords: List[str],
        target_tables: List[str],
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        """执行收集postgressnapshot相关逻辑，并为当前模块提供可复用的处理能力。"""
        conn = await asyncpg.connect(dsn=dsn, timeout=timeout_seconds)  # type: ignore[union-attr]
        try:
            table_records = await conn.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = $1 AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                schema,
            )
            all_table_rows = [str(row["table_name"]) for row in table_records]
            normalized_targets = {self._normalize_table_name(value) for value in (target_tables or []) if self._normalize_table_name(value)}
            table_rows = [name for name in all_table_rows if self._normalize_table_name(name) in normalized_targets] if normalized_targets else list(all_table_rows)
            used_target_tables = bool(normalized_targets)
            fallback_reason = ""
            if used_target_tables and not table_rows:
                table_rows = list(all_table_rows)
                fallback_reason = "mapped_tables_not_found_fallback_all"

            table_structures: List[Dict[str, Any]] = []
            indexes: Dict[str, List[Dict[str, Any]]] = {}
            for table_name in table_rows[:50]:
                column_rows = await conn.fetch(
                    """
                    SELECT column_name, data_type, is_nullable, column_default, ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = $1 AND table_name = $2
                    ORDER BY ordinal_position
                    """,
                    schema,
                    table_name,
                )
                columns = [
                    {
                        "name": str(row["column_name"]),
                        "type": str(row["data_type"] or ""),
                        "notnull": str(row["is_nullable"] or "").upper() == "NO",
                        "default": row["column_default"],
                    }
                    for row in column_rows
                ]
                table_structures.append({"table": table_name, "columns": columns})

                index_rows = await conn.fetch(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = $1 AND tablename = $2
                    ORDER BY indexname
                    """,
                    schema,
                    table_name,
                )
                indexes[table_name] = [
                    {
                        "index": str(row["indexname"]),
                        "definition": str(row["indexdef"] or ""),
                        "unique": " UNIQUE " in str(row["indexdef"] or "").upper(),
                    }
                    for row in index_rows
                ]

            slow_sql = await self._pg_fetch_rows(
                conn,
                [
                    "SELECT query, calls, total_exec_time, mean_exec_time, rows FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT $1",
                    "SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT $1",
                ],
                max_rows,
            )
            top_sql = await self._pg_fetch_rows(
                conn,
                [
                    "SELECT query, calls, total_exec_time, mean_exec_time, rows FROM pg_stat_statements ORDER BY calls DESC LIMIT $1",
                    "SELECT query, calls FROM pg_stat_statements ORDER BY calls DESC LIMIT $1",
                ],
                max_rows,
            )
            session_status = await self._pg_fetch_rows(
                conn,
                [
                    """
                    SELECT COALESCE(state, 'unknown') AS state,
                           COALESCE(wait_event_type, '') AS wait_event_type,
                           COALESCE(wait_event, '') AS wait_event,
                           COUNT(*)::int AS sessions
                    FROM pg_stat_activity
                    GROUP BY state, wait_event_type, wait_event
                    ORDER BY sessions DESC
                    LIMIT $1
                    """,
                    """
                    SELECT COALESCE(state, 'unknown') AS state,
                           COUNT(*)::int AS sessions
                    FROM pg_stat_activity
                    GROUP BY state
                    ORDER BY sessions DESC
                    LIMIT $1
                    """,
                ],
                max_rows,
            )

            keyword_hits: List[Dict[str, Any]] = []
            lowered_keywords = [str(word or "").lower().strip() for word in (keywords or []) if str(word or "").strip()]
            if lowered_keywords:
                for row in (slow_sql + top_sql)[:200]:
                    text = json.dumps(row, ensure_ascii=False).lower()
                    if any(k and k in text for k in lowered_keywords):
                        keyword_hits.append(row)
                        if len(keyword_hits) >= max_rows:
                            break

            return {
                "engine": "postgresql",
                "schema": schema,
                "requested_tables": list(target_tables or [])[:20],
                "used_target_tables": used_target_tables,
                "fallback_reason": fallback_reason,
                "total_table_count": len(all_table_rows),
                "table_count": len(table_rows),
                "tables": table_rows[:80],
                "table_structures": table_structures[:20],
                "indexes": indexes,
                "slow_sql": slow_sql[:max_rows],
                "top_sql": top_sql[:max_rows],
                "session_status": session_status[:max_rows],
                "keyword_hits": keyword_hits[:max_rows],
            }
        finally:
            await conn.close()

    def _collect_database_snapshot(
        self,
        db_path: Path,
        max_rows: int,
        keywords: List[str],
        target_tables: List[str],
    ) -> Dict[str, Any]:
        """执行收集databasesnapshot相关逻辑，并为当前模块提供可复用的处理能力。"""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            all_table_rows = [str(row["name"]) for row in cur.fetchall()]
            normalized_targets = {self._normalize_table_name(value) for value in (target_tables or []) if self._normalize_table_name(value)}
            table_rows = [name for name in all_table_rows if self._normalize_table_name(name) in normalized_targets] if normalized_targets else list(all_table_rows)
            used_target_tables = bool(normalized_targets)
            fallback_reason = ""
            if used_target_tables and not table_rows:
                table_rows = list(all_table_rows)
                fallback_reason = "mapped_tables_not_found_fallback_all"

            table_structures: List[Dict[str, Any]] = []
            indexes: Dict[str, List[Dict[str, Any]]] = {}
            for table_name in table_rows[:50]:
                safe = self._escape_sql_identifier(table_name)
                cur.execute(f"PRAGMA table_info('{safe}')")
                columns = [
                    {
                        "name": str(r["name"]),
                        "type": str(r["type"] or ""),
                        "notnull": bool(r["notnull"]),
                        "default": r["dflt_value"],
                        "pk": bool(r["pk"]),
                    }
                    for r in cur.fetchall()
                ]
                table_structures.append({"table": table_name, "columns": columns})
                cur.execute(f"PRAGMA index_list('{safe}')")
                idx_rows = []
                for idx in cur.fetchall():
                    idx_name = str(idx["name"])
                    unique = bool(idx["unique"])
                    cur.execute(f"PRAGMA index_info('{self._escape_sql_identifier(idx_name)}')")
                    cols = [str(x["name"]) for x in cur.fetchall()]
                    idx_rows.append({"index": idx_name, "unique": unique, "columns": cols})
                indexes[table_name] = idx_rows

            slow_sql = self._query_first_existing(
                cur,
                [
                    "SELECT * FROM slow_sql ORDER BY duration_ms DESC LIMIT ?",
                    "SELECT * FROM slow_sql ORDER BY elapsed_ms DESC LIMIT ?",
                    "SELECT * FROM slow_sql ORDER BY cost_ms DESC LIMIT ?",
                    "SELECT * FROM slow_sql LIMIT ?",
                    "SELECT * FROM t_slow_sql ORDER BY duration_ms DESC LIMIT ?",
                    "SELECT * FROM t_slow_sql ORDER BY elapsed_ms DESC LIMIT ?",
                    "SELECT * FROM t_slow_sql ORDER BY cost_ms DESC LIMIT ?",
                    "SELECT * FROM t_slow_sql LIMIT ?",
                ],
                [max_rows],
            )
            top_sql = self._query_first_existing(
                cur,
                [
                    "SELECT * FROM top_sql ORDER BY exec_count DESC LIMIT ?",
                    "SELECT * FROM top_sql ORDER BY qps DESC LIMIT ?",
                    "SELECT * FROM top_sql ORDER BY calls DESC LIMIT ?",
                    "SELECT * FROM top_sql LIMIT ?",
                    "SELECT * FROM t_top_sql ORDER BY exec_count DESC LIMIT ?",
                    "SELECT * FROM t_top_sql ORDER BY qps DESC LIMIT ?",
                    "SELECT * FROM t_top_sql ORDER BY calls DESC LIMIT ?",
                    "SELECT * FROM t_top_sql LIMIT ?",
                ],
                [max_rows],
            )
            session_status = self._query_first_existing(
                cur,
                [
                    "SELECT * FROM session_status ORDER BY active_sessions DESC LIMIT ?",
                    "SELECT * FROM session_status ORDER BY running DESC LIMIT ?",
                    "SELECT * FROM session_status LIMIT ?",
                    "SELECT * FROM db_session_status ORDER BY active_sessions DESC LIMIT ?",
                    "SELECT * FROM db_session_status ORDER BY running DESC LIMIT ?",
                    "SELECT * FROM db_session_status LIMIT ?",
                ],
                [max_rows],
            )

            keyword_hits: List[Dict[str, Any]] = []
            lowered_keywords = [str(word or "").lower().strip() for word in (keywords or []) if str(word or "").strip()]
            if lowered_keywords:
                for row in (slow_sql + top_sql)[:200]:
                    text = json.dumps(row, ensure_ascii=False).lower()
                    if any(k and k in text for k in lowered_keywords):
                        keyword_hits.append(row)
                        if len(keyword_hits) >= max_rows:
                            break

            return {
                "engine": "sqlite",
                "db_path": str(db_path),
                "requested_tables": list(target_tables or [])[:20],
                "used_target_tables": used_target_tables,
                "fallback_reason": fallback_reason,
                "total_table_count": len(all_table_rows),
                "table_count": len(table_rows),
                "tables": table_rows[:80],
                "table_structures": table_structures[:20],
                "indexes": indexes,
                "slow_sql": slow_sql[:max_rows],
                "top_sql": top_sql[:max_rows],
                "session_status": session_status[:max_rows],
                "keyword_hits": keyword_hits[:max_rows],
            }
        finally:
            conn.close()

    @staticmethod
    def _query_first_existing(cur: sqlite3.Cursor, queries: List[str], params: List[Any]) -> List[Dict[str, Any]]:
        """执行queryfirstexisting相关逻辑，并为当前模块提供可复用的处理能力。"""
        for sql in queries:
            try:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
            except Exception:
                continue
        return []

    @staticmethod
    async def _pg_fetch_rows(conn: Any, queries: List[str], max_rows: int) -> List[Dict[str, Any]]:
        """执行pg抓取rows相关逻辑，并为当前模块提供可复用的处理能力。"""
        for sql in queries:
            try:
                rows = await conn.fetch(sql, max_rows)
                return [dict(row) for row in rows]
            except Exception:
                continue
        return []

    @staticmethod
    def _escape_sql_identifier(name: str) -> str:
        """执行escapesqlidentifier相关逻辑，并为当前模块提供可复用的处理能力。"""
        return str(name or "").replace("'", "''")

    def _decide_tool_invocation(
        self,
        *,
        agent_name: str,
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """根据命令文本和显式开关决定本轮是否允许工具调用。"""
        command = dict(assigned_command or {})
        text_fields = [
            str(command.get("task") or "").strip(),
            str(command.get("focus") or "").strip(),
            str(command.get("expected_output") or "").strip(),
        ]
        skill_hints = command.get("skill_hints")
        has_skill_hints = isinstance(skill_hints, list) and bool(
            [str(item or "").strip() for item in skill_hints if str(item or "").strip()]
        )
        has_command = bool(any(text_fields)) or ("use_tool" in command) or has_skill_hints
        if not has_command:
            return {
                "agent_name": agent_name,
                "has_command": False,
                "allow_tool": False,
                "reason": "未收到主Agent命令",
                "decision_source": "no_command",
            }

        use_tool_raw = command.get("use_tool")
        if isinstance(use_tool_raw, bool):
            return {
                "agent_name": agent_name,
                "has_command": True,
                "allow_tool": use_tool_raw,
                "reason": "主Agent命令显式指定工具开关",
                "decision_source": "explicit_boolean",
            }

        merged = " ".join(text_fields).lower()
        disable_terms = ("无需工具", "不要调用工具", "禁止调用工具", "仅基于现有信息", "不查日志", "不查代码", "不查责任田")
        if any(term in merged for term in disable_terms):
            return {
                "agent_name": agent_name,
                "has_command": True,
                "allow_tool": False,
                "reason": "主Agent命令要求不调用工具",
                "decision_source": "command_text_negative",
            }

        enable_terms = (
            "读取日志",
            "查询日志",
            "检索代码",
            "搜索仓库",
            "查责任田",
            "excel",
            "csv",
            "git",
            "repo",
            "指标",
            "监控",
            "cpu",
            "线程",
            "连接池",
            "grafana",
            "apm",
            "trace",
            "链路",
            "变更",
            "发布",
            "commit",
            "runbook",
            "案例库",
            "sop",
            "日志云",
            "logcloud",
            "告警平台",
            "alert",
            "数据库",
            "慢sql",
            "top sql",
            "索引",
            "表结构",
            "session",
        )
        if any(term in merged for term in enable_terms):
            return {
                "agent_name": agent_name,
                "has_command": True,
                "allow_tool": True,
                "reason": "主Agent命令要求外部证据检索",
                "decision_source": "command_text_positive",
            }

        return {
            "agent_name": agent_name,
            "has_command": True,
            "allow_tool": True,
            "reason": "收到主Agent命令，按Agent默认工具策略执行",
            "decision_source": "command_default",
        }

    def _command_preview(self, assigned_command: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """执行commandpreview相关逻辑，并为当前模块提供可复用的处理能力。"""
        command = dict(assigned_command or {})
        skill_hints_raw = command.get("skill_hints")
        skill_hints = (
            [str(item or "").strip()[:80] for item in skill_hints_raw if str(item or "").strip()]
            if isinstance(skill_hints_raw, list)
            else []
        )
        return {
            "task": str(command.get("task") or "")[:240],
            "focus": str(command.get("focus") or "")[:240],
            "expected_output": str(command.get("expected_output") or "")[:240],
            "use_tool": command.get("use_tool"),
            "skill_hints": skill_hints[:8],
        }

    def _audit(
        self,
        *,
        tool_name: str,
        action: str,
        status: str,
        detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成标准化工具审计记录，统一请求/响应摘要和明细预览。"""
        detail_payload = detail if isinstance(detail, dict) else {"value": str(detail or "")}
        call_id = self._next_audit_call_id(tool_name=tool_name, action=action)
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "call_id": call_id,
            "tool_name": tool_name,
            "action": action,
            "status": status,
            "request_summary": self._request_summary(detail_payload),
            "response_summary": self._response_summary(detail_payload),
            "detail_preview": self._detail_preview(detail_payload),
            "duration_ms": self._coerce_duration_ms(detail_payload),
            "detail": detail_payload,
        }

    def _next_audit_call_id(self, *, tool_name: str, action: str) -> str:
        """执行nextaudit调用id相关逻辑，并为当前模块提供可复用的处理能力。"""
        self._audit_seq += 1
        tool = re.sub(r"[^a-z0-9]+", "_", str(tool_name or "tool").lower()).strip("_") or "tool"
        act = re.sub(r"[^a-z0-9]+", "_", str(action or "action").lower()).strip("_") or "action"
        return f"{tool}_{act}_{self._audit_seq:06d}"

    def _detail_preview(self, detail: Dict[str, Any], *, max_chars: int = 420) -> str:
        """执行detailpreview相关逻辑，并为当前模块提供可复用的处理能力。"""
        try:
            text = json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = str(detail)
        text = str(text or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}..."

    def _request_summary(self, detail: Dict[str, Any]) -> str:
        """执行request摘要相关逻辑，并为当前模块提供可复用的处理能力。"""
        picks: List[str] = []
        for key in ("path", "repo_url", "endpoint", "sheet_name", "keywords", "query", "service_name"):
            value = detail.get(key)
            if value in (None, "", [], {}):
                continue
            picks.append(f"{key}={str(value)[:100]}")
        return "；".join(picks)[:260]

    def _response_summary(self, detail: Dict[str, Any]) -> str:
        """执行response摘要相关逻辑，并为当前模块提供可复用的处理能力。"""
        picks: List[str] = []
        for key in (
            "status",
            "hits_count",
            "lines_count",
            "matches_count",
            "match_count",
            "result_count",
            "error",
        ):
            value = detail.get(key)
            if value in (None, "", [], {}):
                continue
            picks.append(f"{key}={str(value)[:100]}")
        return "；".join(picks)[:260]

    def _coerce_duration_ms(self, detail: Dict[str, Any]) -> Optional[float]:
        """执行coercedurationms相关逻辑，并为当前模块提供可复用的处理能力。"""
        for key in ("duration_ms", "latency_ms", "elapsed_ms"):
            value = detail.get(key)
            if value is None:
                continue
            try:
                return round(float(value), 2)
            except Exception:
                continue
        return None

    def _sanitize_command_part(self, item: str) -> str:
        """执行sanitizecommandpart相关逻辑，并为当前模块提供可复用的处理能力。"""
        text = str(item or "")
        masked = self._mask_url_secret(text)
        return re.sub(r"(?i)(token|apikey|api_key|access_token)=([^&\s]+)", r"\1=***", masked)

    def _mask_url_secret(self, raw_url: str) -> str:
        """执行maskurlsecret相关逻辑，并为当前模块提供可复用的处理能力。"""
        raw = str(raw_url or "").strip()
        if not raw:
            return raw
        try:
            parts = urlsplit(raw)
        except Exception:
            return raw
        if not parts.scheme or not parts.netloc:
            return raw
        netloc = parts.netloc
        if "@" in netloc:
            userinfo, host = netloc.rsplit("@", 1)
            username = userinfo.split(":", 1)[0] if userinfo else "user"
            netloc = f"{username}:***@{host}"
        safe_query = re.sub(r"(?i)(token|apikey|api_key|access_token)=([^&]+)", r"\1=***", parts.query or "")
        return urlunsplit((parts.scheme, netloc, parts.path, safe_query, parts.fragment))

    def _extract_keywords(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
    ) -> List[str]:
        """对输入执行提取keywords，将原始数据整理为稳定的内部结构。"""
        bucket: List[str] = []
        leads = self._extract_investigation_leads(compact_context, incident_context, assigned_command)
        endpoint = (((compact_context.get("interface_mapping") or {}).get("endpoint") or {}) if isinstance(compact_context.get("interface_mapping"), dict) else {})
        for key in ("path", "service", "interface", "method"):
            value = str(endpoint.get(key) or "").strip()
            if value:
                bucket.append(value)
        for field in (
            "api_endpoints",
            "service_names",
            "code_artifacts",
            "class_names",
            "monitor_items",
            "dependency_services",
            "trace_ids",
            "error_keywords",
        ):
            for value in leads.get(field) or []:
                bucket.append(value)
        for table in self._extract_database_tables(compact_context, incident_context, assigned_command):
            bucket.append(table)
        parsed = compact_context.get("parsed_data") or {}
        if isinstance(parsed, dict):
            for key in ("error_type", "error_message", "exception_class", "trace_id"):
                value = str(parsed.get(key) or "").strip()
                if value:
                    bucket.append(value)
        log_excerpt = str(compact_context.get("log_excerpt") or "")
        if log_excerpt:
            bucket.append(log_excerpt[:300])
        for key in ("task", "focus", "expected_output"):
            value = str((assigned_command or {}).get(key) or "").strip()
            if value:
                bucket.append(value)
        full_log = str(incident_context.get("log_content") or "")
        if full_log:
            bucket.append(full_log[:500])

        tokens: List[str] = []
        for raw in bucket:
            for token in re.split(r"[\s,;:|/\\\[\]\(\)\{\}\"'`]+", raw):
                tk = token.strip().lower()
                if len(tk) < 3:
                    continue
                if tk.isdigit():
                    continue
                if tk in {"http", "https", "error", "warn", "info", "debug"}:
                    continue
                tokens.append(tk[:80])
        deduped = list(dict.fromkeys(tokens))
        return deduped[:20]

    def _extract_investigation_leads(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """从命令、compact_context、incident_context 中抽取统一的调查线索包。"""
        picks: Dict[str, List[str]] = {
            "api_endpoints": [],
            "service_names": [],
            "code_artifacts": [],
            "class_names": [],
            "database_tables": [],
            "monitor_items": [],
            "dependency_services": [],
            "trace_ids": [],
            "error_keywords": [],
        }
        scalar = {"domain": "", "aggregate": "", "owner_team": "", "owner": ""}
        command = dict(assigned_command or {})
        sources = [
            command,
            compact_context.get("investigation_leads") if isinstance(compact_context.get("investigation_leads"), dict) else {},
            incident_context.get("investigation_leads") if isinstance(incident_context.get("investigation_leads"), dict) else {},
        ]
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in picks:
                for item in source.get(key) or []:
                    text = str(item or "").strip()
                    if text:
                        picks[key].append(text[:180])
            for key in scalar:
                if not scalar[key]:
                    scalar[key] = str(source.get(key) or "").strip()[:120]
        normalized = {key: list(dict.fromkeys(value))[:20] for key, value in picks.items()}
        normalized.update(scalar)
        return normalized

    def _extract_database_tables(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
    ) -> List[str]:
        """提取并规范化数据库表线索，统一返回有序去重后的表名列表。"""
        picks: List[str] = []
        command = dict(assigned_command or {})
        for table in command.get("database_tables") or []:
            text = str(table or "").strip()
            if text:
                picks.append(text[:120])
        interface_mapping = compact_context.get("interface_mapping")
        if isinstance(interface_mapping, dict):
            for table in (interface_mapping.get("database_tables") or interface_mapping.get("db_tables") or []):
                text = str(table or "").strip()
                if text:
                    picks.append(text[:120])
        incident_mapping = incident_context.get("interface_mapping")
        if isinstance(incident_mapping, dict):
            for table in (incident_mapping.get("database_tables") or incident_mapping.get("db_tables") or []):
                text = str(table or "").strip()
                if text:
                    picks.append(text[:120])
        for table in self._extract_investigation_leads(compact_context, incident_context, assigned_command).get("database_tables") or []:
            text = str(table or "").strip()
            if text:
                picks.append(text[:120])
        # keep order and unique
        return list(dict.fromkeys(picks))[:20]

    def _primary_service_name(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
    ) -> str:
        """返回最可信的服务名，供日志、指标、代码和变更工具共享。"""
        leads = self._extract_investigation_leads(compact_context, incident_context, assigned_command)
        candidates = [
            incident_context.get("service_name"),
            ((compact_context.get("interface_mapping") or {}).get("endpoint") or {}).get("service") if isinstance(compact_context.get("interface_mapping"), dict) else "",
            *((leads.get("service_names") or [])[:4]),
        ]
        for item in candidates:
            text = str(item or "").strip()
            if text:
                return text[:160]
        return ""

    def _primary_trace_id(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
    ) -> str:
        """返回最可信的 Trace ID，供日志/APM 等链路工具复用。"""
        leads = self._extract_investigation_leads(compact_context, incident_context, assigned_command)
        candidates = [
            incident_context.get("trace_id"),
            ((compact_context.get("parsed_data") or {}).get("trace_id") if isinstance(compact_context.get("parsed_data"), dict) else ""),
            *((leads.get("trace_ids") or [])[:4]),
        ]
        for item in candidates:
            text = str(item or "").strip()
            if text:
                return text[:160]
        return ""

    @staticmethod
    def _normalize_table_name(name: str) -> str:
        """对输入执行归一化tablename，将原始数据整理为稳定的内部结构。"""
        text = str(name or "").strip().lower().strip('"')
        if "." in text:
            return text.split(".")[-1].strip('"')
        return text

    def _search_repo(
        self,
        repo_path: str,
        keywords: List[str],
        max_hits: int,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """在本地代码仓执行受限搜索，返回结构化命中片段和扫描摘要。"""
        path = Path(repo_path)
        if not path.exists():
            return [], {"repo_path": repo_path, "files_scanned": 0, "hits": 0}
        hits: List[Dict[str, Any]] = []
        scanned_files = 0
        matched_files = 0
        lowered_keywords = [k.lower() for k in keywords if k]
        if not lowered_keywords:
            lowered_keywords = ["exception", "error", "timeout", "order"]

        for file in path.rglob("*"):
            if len(hits) >= max_hits:
                break
            if not file.is_file():
                continue
            if any(part in {".git", "node_modules", "dist", "build", "__pycache__"} for part in file.parts):
                continue
            if file.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            scanned_files += 1
            try:
                content = file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            file_hit = False
            for index, line in enumerate(content.splitlines(), start=1):
                line_low = line.lower()
                keyword = next((kw for kw in lowered_keywords if kw in line_low), "")
                if not keyword:
                    continue
                file_hit = True
                hits.append(
                    {
                        "file": str(file.relative_to(path)),
                        "line": index,
                        "keyword": keyword,
                        "snippet": line.strip()[:220],
                    }
                )
                if len(hits) >= max_hits:
                    break
            if file_hit:
                matched_files += 1
        return hits, {
            "repo_path": str(path),
            "files_scanned": scanned_files,
            "files_with_hits": matched_files,
            "hits": len(hits),
            "keywords": lowered_keywords[:8],
        }

    def _read_log_excerpt(
        self,
        path: Path,
        max_lines: int,
        keywords: Iterable[str],
    ) -> tuple[str, int, Dict[str, Any]]:
        """从日志文件提取局部窗口，优先返回命中关键词的片段。"""
        kw = [k.lower() for k in keywords if k]
        window = deque(maxlen=max(50, max_lines))
        scanned_lines = 0
        matched_lines = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                scanned_lines += 1
                text = line.rstrip("\n")
                if not kw or any(item in text.lower() for item in kw):
                    matched_lines += 1
                    window.append(text)
        if not window:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    window.append(line.rstrip("\n"))
        lines = list(window)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return (
            "\n".join(lines),
            len(lines),
            {
                "file_path": str(path),
                "scanned_lines": scanned_lines,
                "matched_lines": matched_lines,
                "returned_lines": len(lines),
                "keywords": kw[:10],
            },
        )

    def _lookup_domain_file(
        self,
        path: Path,
        sheet_name: str,
        max_rows: int,
        max_matches: int,
        keywords: List[str],
    ) -> Dict[str, Any]:
        """从责任田/领域文件中查找与当前关键词最相关的记录。"""
        suffix = path.suffix.lower()
        sheet_used = ""
        if suffix == ".csv":
            rows = self._read_csv_rows(path, max_rows=max_rows)
        elif suffix in {".xlsx", ".xlsm"}:
            rows, sheet_used = self._read_xlsx_rows(path, sheet_name=sheet_name, max_rows=max_rows)
        else:
            raise RuntimeError("仅支持 .csv/.xlsx/.xlsm")

        lowered = [k.lower() for k in keywords if k]
        matches: List[Dict[str, Any]] = []
        for row in rows:
            merged = " | ".join(str(v) for v in row.values()).lower()
            if lowered and not any(k in merged for k in lowered):
                continue
            matches.append(row)
            if len(matches) >= max_matches:
                break
        if not lowered:
            matches = rows[:max_matches]
        return {
            "format": suffix,
            "sheet_used": sheet_used,
            "row_count": len(rows),
            "matches": matches,
        }

    def _read_csv_rows(self, path: Path, max_rows: int) -> List[Dict[str, Any]]:
        """负责读取csvrows，并返回后续流程可直接消费的数据结果。"""
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for idx, row in enumerate(reader, start=1):
                rows.append({str(k): str(v) for k, v in (row or {}).items()})
                if idx >= max_rows:
                    break
        return rows

    def _read_xlsx_rows(self, path: Path, sheet_name: str, max_rows: int) -> tuple[List[Dict[str, Any]], str]:
        """负责读取xlsxrows，并返回后续流程可直接消费的数据结果。"""
        try:
            from openpyxl import load_workbook  # type: ignore
        except Exception as exc:
            raise RuntimeError("读取 xlsx 需要安装 openpyxl") from exc
        wb = load_workbook(filename=str(path), read_only=True, data_only=True)
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb[wb.sheetnames[0]]
        rows_iter = ws.iter_rows(values_only=True)
        headers_raw = next(rows_iter, None) or []
        headers = [str(h or f"col_{i+1}") for i, h in enumerate(headers_raw)]
        rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows_iter, start=1):
            rows.append({headers[i]: str(value or "") for i, value in enumerate(row or []) if i < len(headers)})
            if idx >= max_rows:
                break
        wb.close()
        return rows, str(ws.title or "")

    def _resolve_log_excerpt(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        tool_context: Optional[Dict[str, Any]],
    ) -> str:
        tool_data = (tool_context or {}).get("data") if isinstance(tool_context, dict) else {}
        if isinstance(tool_data, dict):
            excerpt = str(tool_data.get("excerpt") or "").strip()
            if excerpt:
                return excerpt
        for source in (
            str(compact_context.get("log_excerpt") or "").strip(),
            str(incident_context.get("log_content") or "").strip(),
            str(incident_context.get("description") or "").strip(),
        ):
            if source:
                return source
        return ""

    def _extract_log_timeline(self, excerpt: str, *, max_events: int) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        if not excerpt:
            return events
        for raw_line in excerpt.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            timestamp_match = re.search(r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)", line)
            if not timestamp_match:
                timestamp_match = re.search(r"(\d{2}:\d{2}:\d{2})", line)
            level_match = re.search(r"\b(INFO|WARN|ERROR|DEBUG|TRACE)\b", line, flags=re.IGNORECASE)
            component_match = re.search(r"\b([a-zA-Z_][\w.$-]{6,})\b", line)
            events.append(
                {
                    "timestamp": str(timestamp_match.group(1) if timestamp_match else "")[:64],
                    "level": str(level_match.group(1).upper() if level_match else "")[:12],
                    "component": str(component_match.group(1) if component_match else "")[:120],
                    "message": line[:320],
                }
            )
            if len(events) >= max_events:
                break
        return events

    def _build_log_causal_timeline(self, timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chain: List[Dict[str, Any]] = []
        first_error_added = False
        resource_added = False
        user_visible_added = False
        for item in timeline:
            message = str(item.get("message") or "").lower()
            level = str(item.get("level") or "").upper()
            stage = ""
            rationale = ""
            if any(term in message for term in ("uri=", "post /api", "get /api", "request start", "createorder start")):
                stage = "request_entry"
                rationale = "请求进入系统，构成时间线起点。"
            elif not first_error_added and level == "ERROR":
                stage = "first_error"
                rationale = "首个错误事件，通常是应用侧初始异常。"
                first_error_added = True
            if not resource_added and any(term in message for term in ("connection is not available", "lock wait", "timeout after", "pending", "pool")):
                stage = "resource_exhaustion"
                rationale = "资源耗尽或阻塞放大，可能是故障扩散关键节点。"
                resource_added = True
            if any(term in message for term in ("status=502", "5xx", "upstream timeout", "bad gateway")):
                stage = "user_visible_failure"
                rationale = "用户可见错误，代表故障已经暴露到入口层。"
                user_visible_added = True
            if not stage:
                continue
            chain.append(
                {
                    "stage": stage,
                    "timestamp": str(item.get("timestamp") or ""),
                    "component": str(item.get("component") or ""),
                    "message": str(item.get("message") or "")[:280],
                    "rationale": rationale,
                }
            )
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in chain:
            key = f"{item.get('stage')}|{item.get('timestamp')}|{item.get('component')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:8]

    def _load_repo_focus_windows(
        self,
        *,
        repo_path: str,
        candidate_files: List[str],
        max_files: int,
        max_chars: int,
    ) -> List[Dict[str, Any]]:
        root = Path(str(repo_path or "").strip())
        if not root.exists() or not root.is_dir():
            return []
        windows: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw_name in candidate_files:
            name = str(raw_name or "").strip()
            if not name:
                continue
            normalized = name.lstrip("./")
            if normalized in seen:
                continue
            seen.add(normalized)
            direct = root / normalized
            file_path: Optional[Path] = None
            if direct.exists() and direct.is_file():
                file_path = direct
            else:
                matches = list(root.rglob(Path(normalized).name))
                for item in matches:
                    if item.is_file():
                        try:
                            rel = str(item.relative_to(root))
                        except Exception:
                            rel = str(item)
                        if rel.endswith(normalized) or item.name == Path(normalized).name:
                            file_path = item
                            break
            if file_path is None:
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            windows.append(
                {
                    "file": str(file_path.relative_to(root)),
                    "excerpt": text[:max_chars],
                }
            )
            if len(windows) >= max_files:
                break
        return windows

    def _expand_related_code_files(
        self,
        *,
        repo_path: str,
        seed_files: List[str],
        class_hints: List[str],
        depth: int,
        per_hop_limit: int,
    ) -> List[str]:
        root = Path(str(repo_path or "").strip())
        if not root.exists() or not root.is_dir():
            return []
        queue: List[str] = [str(item or "").strip() for item in seed_files if str(item or "").strip()]
        related: List[str] = []
        seen_files = set(queue)
        seen_symbols: set[str] = set()
        explicit_symbols = [str(item or "").strip() for item in class_hints if str(item or "").strip()]
        for symbol in explicit_symbols:
            symbol_file = self._find_symbol_file(root, symbol)
            if symbol_file is None:
                continue
            try:
                rel = str(symbol_file.relative_to(root))
            except Exception:
                rel = str(symbol_file)
            seen_symbols.add(symbol)
            if rel in seen_files:
                continue
            seen_files.add(rel)
            related.append(rel)
            queue.append(rel)
        for _ in range(max(1, depth)):
            if not queue:
                break
            next_queue: List[str] = []
            hop_found = 0
            for item in list(queue):
                file_path = self._resolve_repo_file(root, item)
                if file_path is None:
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for symbol in self._extract_related_code_symbols(text):
                    if symbol in seen_symbols:
                        continue
                    seen_symbols.add(symbol)
                    symbol_file = self._find_symbol_file(root, symbol)
                    if symbol_file is None:
                        continue
                    try:
                        rel = str(symbol_file.relative_to(root))
                    except Exception:
                        rel = str(symbol_file)
                    if rel in seen_files:
                        continue
                    seen_files.add(rel)
                    related.append(rel)
                    next_queue.append(rel)
                    hop_found += 1
                    if hop_found >= per_hop_limit:
                        break
                if hop_found >= per_hop_limit:
                    break
            queue = next_queue
        return related

    def _resolve_repo_file(self, root: Path, raw_name: str) -> Optional[Path]:
        normalized = str(raw_name or "").strip().lstrip("./")
        if not normalized:
            return None
        direct = root / normalized
        if direct.exists() and direct.is_file():
            return direct
        for item in root.rglob(Path(normalized).name):
            if item.is_file():
                try:
                    rel = str(item.relative_to(root))
                except Exception:
                    rel = str(item)
                if rel.endswith(normalized) or item.name == Path(normalized).name:
                    return item
        return None

    def _find_symbol_file(self, root: Path, symbol: str) -> Optional[Path]:
        for suffix in SOURCE_SUFFIXES:
            candidate = list(root.rglob(f"{symbol}{suffix}"))
            for item in candidate:
                if item.is_file():
                    return item
        return None

    def _extract_related_code_symbols(self, text: str) -> List[str]:
        symbols: List[str] = []
        for match in re.finditer(
            r"\b([A-Z][A-Za-z0-9_]{2,}(?:Controller|Service|AppService|Repository|Repo|Mapper|Dao|Client|Gateway|Manager))\b",
            text,
        ):
            symbol = str(match.group(1) or "").strip()
            if symbol:
                symbols.append(symbol)
        return list(dict.fromkeys(symbols))[:24]

    def _build_method_call_chain(
        self,
        *,
        repo_path: str,
        endpoint_interface: str,
        code_windows: List[Dict[str, Any]],
        hit_snippets: List[str],
    ) -> List[Dict[str, Any]]:
        root = Path(str(repo_path or "").strip())
        if not root.exists() or not root.is_dir():
            return []
        parsed = self._parse_interface_ref(endpoint_interface)
        files = [str(item.get("file") or "").strip() for item in code_windows if str(item.get("file") or "").strip()]
        source_units = self._load_source_units(root, files[:8])
        if not source_units:
            return []

        entry_symbol = parsed.get("symbol") or source_units[0].get("symbol") or ""
        entry_method = parsed.get("method") or self._guess_entry_method(source_units, hit_snippets)
        if not entry_method:
            return []
        start_unit = self._find_source_unit(source_units, entry_symbol, preferred_file=files[0] if files else "")
        if not start_unit:
            start_unit = source_units[0]
        chain: List[Dict[str, Any]] = []
        visited: set[str] = set()
        current_symbol = str(start_unit.get("symbol") or "")
        current_method = entry_method
        for _ in range(4):
            unit = self._find_source_unit(source_units, current_symbol)
            if not unit:
                break
            methods = unit.get("methods") if isinstance(unit.get("methods"), dict) else {}
            method_meta = methods.get(current_method) if isinstance(methods, dict) else None
            if not isinstance(method_meta, dict):
                if not methods:
                    break
                fallback_name, fallback_meta = next(iter(methods.items()))
                current_method = str(fallback_name)
                method_meta = fallback_meta if isinstance(fallback_meta, dict) else {}
            key = f"{current_symbol}#{current_method}"
            if key in visited:
                break
            visited.add(key)
            chain.append(
                {
                    "symbol": current_symbol,
                    "method": current_method,
                    "file": str(unit.get("file") or ""),
                    "line": int(method_meta.get("line") or 0),
                    "snippet": str(method_meta.get("snippet") or "")[:220],
                }
            )
            next_call = self._resolve_next_method_call(
                source_units=source_units,
                current_unit=unit,
                method_meta=method_meta,
            )
            if not next_call:
                break
            current_symbol = str(next_call.get("symbol") or "")
            current_method = str(next_call.get("method") or "")
            if not current_symbol or not current_method:
                break
        return chain

    def _parse_interface_ref(self, raw: str) -> Dict[str, str]:
        text = str(raw or "").strip()
        if not text:
            return {"symbol": "", "method": ""}
        for sep in ("#", ".", "::"):
            if sep in text:
                left, right = text.split(sep, 1)
                return {"symbol": left.strip(), "method": right.strip()}
        return {"symbol": text.strip(), "method": ""}

    def _load_source_units(self, root: Path, files: List[str]) -> List[Dict[str, Any]]:
        units: List[Dict[str, Any]] = []
        for raw_file in files:
            file_path = self._resolve_repo_file(root, raw_file)
            if file_path is None:
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            units.append(self._parse_source_unit(root=root, file_path=file_path, text=text))
        return units

    def _parse_source_unit(self, *, root: Path, file_path: Path, text: str) -> Dict[str, Any]:
        symbol_match = re.search(r"\bclass\s+([A-Z][A-Za-z0-9_]*)\b", text)
        symbol = str(symbol_match.group(1) if symbol_match else file_path.stem)
        fields = self._extract_field_types(text)
        methods = self._extract_methods(text)
        try:
            rel = str(file_path.relative_to(root))
        except Exception:
            rel = str(file_path)
        return {
            "symbol": symbol,
            "file": rel,
            "fields": fields,
            "methods": methods,
        }

    def _extract_field_types(self, text: str) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        for match in re.finditer(
            r"\b(?:private|protected|public)?\s*(?:final\s+)?([A-Z][A-Za-z0-9_<>]*)\s+([a-z][A-Za-z0-9_]*)\s*(?:[;=])",
            text,
        ):
            field_type = str(match.group(1) or "").split("<", 1)[0].strip()
            field_name = str(match.group(2) or "").strip()
            if field_name and field_type:
                fields[field_name] = field_type
        return fields

    def _extract_methods(self, text: str) -> Dict[str, Dict[str, Any]]:
        methods: Dict[str, Dict[str, Any]] = {}
        lines = text.splitlines()
        for idx, line in enumerate(lines, start=1):
            match = re.search(
                r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:[\w<>\[\],?]+\s+)+([a-zA-Z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{?",
                line,
            )
            if not match:
                continue
            method_name = str(match.group(1) or "").strip()
            if method_name in {"if", "for", "while", "switch", "catch", "return", "new"}:
                continue
            body_lines = lines[idx - 1 : min(len(lines), idx + 8)]
            methods[method_name] = {
                "line": idx,
                "snippet": "\n".join(body_lines),
            }
        return methods

    def _guess_entry_method(self, source_units: List[Dict[str, Any]], hit_snippets: List[str]) -> str:
        for snippet in hit_snippets:
            match = re.search(r"\.\s*([a-zA-Z_][A-Za-z0-9_]*)\s*\(", str(snippet or ""))
            if match:
                return str(match.group(1) or "").strip()
        for unit in source_units:
            methods = unit.get("methods") if isinstance(unit.get("methods"), dict) else {}
            for name in methods:
                if name.lower().startswith(("create", "submit", "save", "update", "handle")):
                    return str(name)
        if source_units:
            methods = source_units[0].get("methods") if isinstance(source_units[0].get("methods"), dict) else {}
            if methods:
                return str(next(iter(methods.keys())))
        return ""

    def _find_source_unit(
        self,
        source_units: List[Dict[str, Any]],
        symbol: str,
        *,
        preferred_file: str = "",
    ) -> Optional[Dict[str, Any]]:
        normalized_symbol = str(symbol or "").strip()
        normalized_file = str(preferred_file or "").strip()
        for unit in source_units:
            if normalized_file and str(unit.get("file") or "").strip() == normalized_file:
                return unit
        for unit in source_units:
            if str(unit.get("symbol") or "").strip() == normalized_symbol:
                return unit
        return None

    def _resolve_next_method_call(
        self,
        *,
        source_units: List[Dict[str, Any]],
        current_unit: Dict[str, Any],
        method_meta: Dict[str, Any],
    ) -> Optional[Dict[str, str]]:
        snippet = str(method_meta.get("snippet") or "")
        fields = current_unit.get("fields") if isinstance(current_unit.get("fields"), dict) else {}
        for match in re.finditer(r"\b([a-zA-Z_][A-Za-z0-9_]*)\.([a-zA-Z_][A-Za-z0-9_]*)\s*\(", snippet):
            receiver = str(match.group(1) or "").strip()
            method = str(match.group(2) or "").strip()
            symbol = str(fields.get(receiver) or "").strip()
            if not symbol or method in {"println", "info", "warn", "error", "debug"}:
                continue
            if self._find_source_unit(source_units, symbol):
                return {"symbol": symbol, "method": method}
        return None

    @staticmethod
    def _trim_mapping(value: Any, *, item_limit: int, value_limit: int) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result: Dict[str, Any] = {}
        for key, item in list(value.items())[:item_limit]:
            if isinstance(item, list):
                result[str(key)] = item[:value_limit]
            elif isinstance(item, dict):
                result[str(key)] = dict(list(item.items())[:value_limit])
            else:
                result[str(key)] = item
        return result

    @staticmethod
    def _remote_source_summary(value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {"enabled": False, "status": "unavailable"}
        return {
            "enabled": bool(value.get("enabled")),
            "status": str(value.get("status") or ""),
            "payload_keys": list((value.get("payload") or {}).keys())[:12] if isinstance(value.get("payload"), dict) else [],
        }

    def _summarize_metric_signals(self, signals: List[Dict[str, Any]]) -> List[str]:
        summaries: List[str] = []
        for item in signals:
            metric = str(item.get("label") or item.get("metric") or "").strip()
            value = str(item.get("value") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if not metric or not value:
                continue
            summaries.append(f"{metric}={value}，证据={snippet[:120]}")
            if len(summaries) >= 8:
                break
        return summaries

    def _build_metric_causal_chain(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chain: List[Dict[str, Any]] = []
        for item in signals:
            metric = str(item.get("metric") or "").strip().lower()
            label = str(item.get("label") or metric).strip()
            value = str(item.get("value") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            stage = ""
            rationale = ""
            if metric in {"cpu", "threads", "memory", "gc"}:
                stage = "resource_pressure"
                rationale = "资源指标先行异常，通常代表系统已进入压力阶段。"
            elif metric in {"db_conn", "hikari_pending", "pool", "queue"}:
                stage = "capacity_saturation"
                rationale = "连接/队列类指标打满，说明容量瓶颈已形成。"
            elif metric in {"error_rate", "latency", "p99", "availability", "5xx"}:
                stage = "user_visible_failure"
                rationale = "错误率或延迟已上升到用户可感知层。"
            if not stage:
                continue
            chain.append(
                {
                    "stage": stage,
                    "metric": metric,
                    "label": label,
                    "value": value,
                    "snippet": snippet[:180],
                    "rationale": rationale,
                }
            )
        if not chain:
            return []
        stage_order = {"resource_pressure": 1, "capacity_saturation": 2, "user_visible_failure": 3}
        chain.sort(key=lambda item: (stage_order.get(str(item.get("stage") or ""), 99), str(item.get("metric") or "")))
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in chain:
            key = f"{item.get('stage')}|{item.get('metric')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:8]

    def _extract_runbook_actions(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for item in items:
            runbook_fields = item.get("runbook_fields") if isinstance(item.get("runbook_fields"), dict) else {}
            if runbook_fields:
                steps = list(runbook_fields.get("steps") or [])[:4]
                verify = list(runbook_fields.get("verification_steps") or [])[:3]
            else:
                steps = []
                verify = []
            actions.append(
                {
                    "title": str(item.get("title") or "")[:160],
                    "entry_type": str(item.get("entry_type") or "")[:40],
                    "steps": steps,
                    "verification_steps": verify,
                }
            )
            if len(actions) >= 6:
                break
        return actions

    def _build_database_causal_summary(
        self,
        *,
        target_tables: List[str],
        tool_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        slow_sql = [item for item in list(tool_data.get("slow_sql") or []) if isinstance(item, dict)]
        top_sql = [item for item in list(tool_data.get("top_sql") or []) if isinstance(item, dict)]
        session_status = [item for item in list(tool_data.get("session_status") or []) if isinstance(item, dict)]
        keyword_hits = [item for item in list(tool_data.get("keyword_hits") or []) if isinstance(item, dict)]

        evidence_points: List[str] = []
        likely_causes: List[str] = []
        dominant_pattern = "db_pressure"

        for row in session_status:
            wait_type = str(row.get("wait_event_type") or "").strip()
            wait_event = str(row.get("wait_event") or "").strip()
            sessions = row.get("sessions")
            if wait_type or wait_event:
                evidence_points.append(f"session wait: {wait_type or 'unknown'}/{wait_event or 'unknown'} sessions={sessions}")
            if wait_type.lower() == "lock" or "lock" in wait_event.lower():
                dominant_pattern = "lock_contention"
                likely_causes.append("存在数据库锁等待，事务争用可能是放大点。")

        for row in slow_sql[:3]:
            query = str(row.get("query") or row.get("sql_text") or "")[:180]
            mean_exec_time = row.get("mean_exec_time") or row.get("duration_ms") or row.get("elapsed_ms")
            if query:
                evidence_points.append(f"slow sql: {query} time={mean_exec_time}")
            if "update " in query.lower() or "for update" in query.lower():
                likely_causes.append("慢 SQL 包含写操作，可能造成锁持有时间过长。")

        for row in keyword_hits[:3]:
            query = str(row.get("query") or row.get("sql_text") or "")[:180]
            if query:
                evidence_points.append(f"keyword hit: {query}")

        if not likely_causes and slow_sql:
            likely_causes.append("数据库存在明显慢 SQL，可能导致连接占用升高和上游超时。")
        if not likely_causes and top_sql:
            likely_causes.append("数据库访问压力升高，需结合高频 SQL 判断是否存在热点查询。")

        return {
            "dominant_pattern": dominant_pattern,
            "target_tables": list(target_tables)[:12],
            "likely_causes": list(dict.fromkeys(likely_causes))[:4],
            "evidence_points": list(dict.fromkeys(evidence_points))[:6],
        }

    def _build_domain_causal_summary(
        self,
        *,
        mapping: Dict[str, Any],
        endpoint: Dict[str, Any],
        matches: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        matched = bool(mapping.get("matched"))
        owner_team = str(mapping.get("owner_team") or "")[:120]
        owner = str(mapping.get("owner") or "")[:120]
        domain = str(mapping.get("domain") or "")[:120]
        aggregate = str(mapping.get("aggregate") or "")[:120]
        feature = str(mapping.get("feature") or "")[:120]
        service = str(endpoint.get("service") or "")[:160]
        database_tables = list(mapping.get("database_tables") or mapping.get("db_tables") or [])[:12]
        dependency_services = list(mapping.get("dependency_services") or [])[:10]
        monitor_items = list(mapping.get("monitor_items") or [])[:10]

        evidence_points: List[str] = []
        if matched:
            evidence_points.append(
                f"接口已命中责任田：{domain or '-'} / {aggregate or '-'} / {feature or '-'}"
            )
        if owner_team or owner:
            evidence_points.append(f"责任团队：{owner_team or '-'}；责任人：{owner or '-'}")
        if service:
            evidence_points.append(f"接口归属服务：{service}")
        if matches:
            first = matches[0]
            evidence_points.append(
                f"责任田文档命中：{str(first.get('domain') or domain or '-')}/{str(first.get('aggregate') or aggregate or '-')}"
            )

        return {
            "dominant_pattern": "owner_confirmed" if matched and owner_team else "mapping_gap",
            "owner_team": owner_team,
            "owner": owner,
            "domain": domain,
            "aggregate": aggregate,
            "impact_scope": {
                "service": service,
                "database_tables": database_tables,
                "dependency_services": dependency_services,
                "monitor_items": monitor_items,
            },
            "evidence_points": list(dict.fromkeys(evidence_points))[:6],
        }

    def _build_change_causal_summary(
        self,
        *,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        changes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        leads = self._extract_investigation_leads(compact_context, incident_context, assigned_command)
        endpoint_texts = [
            str(item or "").strip().lower()
            for item in list(leads.get("api_endpoints") or [])
            if str(item or "").strip()
        ]
        service_names = [
            str(item or "").strip().lower()
            for item in list(leads.get("service_names") or [])
            if str(item or "").strip()
        ]
        artifact_names = [
            str(Path(str(item or "")).stem or "").strip().lower()
            for item in list(leads.get("code_artifacts") or [])
            if str(item or "").strip()
        ]
        focus_text = " ".join(
            filter(
                None,
                [
                    str((assigned_command or {}).get("task") or "").strip(),
                    str((assigned_command or {}).get("focus") or "").strip(),
                    str(incident_context.get("description") or "").strip(),
                ],
            )
        ).lower()

        suspect_changes: List[Dict[str, Any]] = []
        mechanism_links: List[str] = []
        evidence_points: List[str] = []
        dominant_pattern = "change_window_noise"

        for change in changes[:12]:
            commit = str(change.get("commit") or "")[:12]
            subject = str(change.get("subject") or "").strip()
            subject_lower = subject.lower()
            score = 0

            if any(service and service in subject_lower for service in service_names):
                score += 2
                mechanism_links.append("变更主题直接命中责任服务，需优先评估是否为发布回归。")
            if any(endpoint and endpoint.split()[-1] in subject_lower for endpoint in endpoint_texts):
                score += 2
                mechanism_links.append("变更主题与问题接口路径相邻，可能影响路由或接口注册。")
            if any(artifact and artifact in subject_lower for artifact in artifact_names):
                score += 2
                mechanism_links.append("变更主题提到责任田代码符号，可能直接触发实现回归。")
            if any(token in subject_lower for token in ("route", "mapping", "controller", "retry", "timeout", "transaction", "pool")):
                score += 1
                mechanism_links.append("变更涉及路由/重试/事务/连接池等敏感机制，可能改变故障放大链。")
            if focus_text and any(token in subject_lower for token in focus_text.split()):
                score += 1

            if subject:
                evidence_points.append(f"{commit}: {subject[:160]}")
            if score >= 2:
                dominant_pattern = "recent_release_regression"
                suspect_changes.append(
                    {
                        "commit": commit,
                        "author": str(change.get("author") or "")[:80],
                        "time": str(change.get("time") or "")[:64],
                        "subject": subject[:200],
                        "score": score,
                    }
                )

        if dominant_pattern == "recent_release_regression":
            mechanism_links.append("近期变更与服务/接口/关键机制同时命中，符合发布后回归的初步特征。")
        elif changes:
            mechanism_links.append("已获取变更窗口，但暂无强匹配项，需要与日志和代码证据交叉验证。")
        else:
            evidence_points.append("变更窗口为空，当前无法从代码提交侧建立直接因果。")

        return {
            "dominant_pattern": dominant_pattern,
            "suspect_changes": suspect_changes[:4],
            "mechanism_links": list(dict.fromkeys(mechanism_links))[:4],
            "evidence_points": list(dict.fromkeys(evidence_points))[:6],
        }

    def _build_runbook_action_summary(
        self,
        *,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        items: List[Dict[str, Any]],
        recommended_actions: List[Dict[str, Any]],
        source: str,
    ) -> Dict[str, Any]:
        service_name = self._primary_service_name(compact_context, incident_context, assigned_command)
        recommended_steps: List[str] = []
        verification_steps: List[str] = []
        evidence_points: List[str] = []
        dominant_pattern = "knowledge_gap"

        for item in items[:6]:
            title = str(item.get("title") or "").strip()
            entry_type = str(item.get("entry_type") or "").strip().lower()
            summary = str(item.get("summary") or "").strip()
            runbook_fields = item.get("runbook_fields") if isinstance(item.get("runbook_fields"), dict) else {}
            steps = [str(value).strip() for value in list(runbook_fields.get("steps") or []) if str(value).strip()]
            verify = [
                str(value).strip()
                for value in list(runbook_fields.get("verification_steps") or [])
                if str(value).strip()
            ]
            if title:
                evidence_points.append(f"{entry_type or 'knowledge'}: {title[:160]}")
            if summary:
                evidence_points.append(summary[:180])
            if entry_type == "runbook" and steps:
                dominant_pattern = "matched_runbook"
                recommended_steps.extend(steps[:3])
                verification_steps.extend(verify[:3])

        if dominant_pattern == "knowledge_gap" and recommended_actions:
            for action in recommended_actions[:3]:
                recommended_steps.extend(
                    [str(value).strip() for value in list(action.get("steps") or []) if str(value).strip()][:2]
                )
                verification_steps.extend(
                    [
                        str(value).strip()
                        for value in list(action.get("verification_steps") or [])
                        if str(value).strip()
                    ][:2]
                )
            if recommended_steps:
                dominant_pattern = "matched_runbook"

        if dominant_pattern == "matched_runbook":
            evidence_points.append(
                f"已命中 {source or 'knowledge'} 中与 {service_name or '当前服务'} 相关的处置知识，可用于止血与验证。"
            )
        else:
            evidence_points.append("当前未命中可直接执行的 Runbook，需要结合专家结论补充处置步骤。")

        return {
            "dominant_pattern": dominant_pattern,
            "service_name": service_name,
            "recommended_steps": list(dict.fromkeys(recommended_steps))[:5],
            "verification_steps": list(dict.fromkeys(verification_steps))[:4],
            "evidence_points": list(dict.fromkeys(evidence_points))[:6],
        }


agent_tool_context_service = AgentToolContextService()
