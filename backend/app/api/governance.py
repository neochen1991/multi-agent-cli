"""Governance center APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.governance.system_card import build_system_card, estimate_cost
from app.runtime.langgraph.strategy_center import runtime_strategy_center
from app.services.feedback_service import feedback_service
from app.services.governance_ops_service import governance_ops_service
from app.services.remediation_service import remediation_service

router = APIRouter()


class FeedbackRequest(BaseModel):
    incident_id: str = Field(default="")
    session_id: str = Field(default="")
    verdict: str = Field(default="adopt", pattern="^(adopt|reject|revise)$")
    comment: str = Field(default="")
    tags: list[str] = Field(default_factory=list)


class RemediationProposeRequest(BaseModel):
    incident_id: str
    session_id: str
    summary: str
    steps: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="medium")
    pre_slo: Dict[str, Any] = Field(default_factory=dict)


class RemediationSimulateRequest(BaseModel):
    simulated_slo: Dict[str, Any] = Field(default_factory=dict)


class RemediationApproveRequest(BaseModel):
    approver: str = Field(default="sre-oncall")
    comment: str = Field(default="")


class RemediationExecuteRequest(BaseModel):
    operator: str = Field(default="sre-oncall")
    post_slo: Dict[str, Any] = Field(default_factory=dict)


class RemediationVerifyRequest(BaseModel):
    verifier: str = Field(default="qa")
    verification: Dict[str, Any] = Field(default_factory=dict)


class RemediationRollbackRequest(BaseModel):
    reason: str = Field(default="")
    execute: bool = Field(default=False)


class RemediationChangeLinkRequest(BaseModel):
    change_id: str
    window: str = Field(default="business-hours")
    release_type: str = Field(default="app")


class TenantPolicyRequest(BaseModel):
    tenant_id: str
    name: str = Field(default="")
    rbac: Dict[str, Any] = Field(default_factory=dict)
    quota: Dict[str, Any] = Field(default_factory=dict)
    budget: Dict[str, Any] = Field(default_factory=dict)
    isolation: Dict[str, Any] = Field(default_factory=dict)


class ExternalSyncRequest(BaseModel):
    provider: str = Field(pattern="^(jira|servicenow|slack|feishu|pagerduty)$")
    direction: str = Field(default="outbound", pattern="^(outbound|inbound)$")
    action: str = Field(default="notify")
    payload: Dict[str, Any] = Field(default_factory=dict)


class ExternalSyncSettingsRequest(BaseModel):
    enabled: bool = Field(default=False)
    providers: List[str] = Field(default_factory=list)


class RuntimeStrategyRequest(BaseModel):
    profile: str = Field(default="balanced")


def _metrics_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "metrics"


def _load_baselines(limit: int = 20) -> List[Dict[str, Any]]:
    files = sorted(_metrics_dir().glob("baseline-*.json"), reverse=True)[: max(1, int(limit))]
    rows: List[Dict[str, Any]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append(
            {
                "file": str(path),
                "generated_at": payload.get("generated_at"),
                "summary": payload.get("summary") or {},
            }
        )
    return rows


@router.get("/system-card", summary="系统边界卡")
async def get_system_card():
    return build_system_card()


@router.get("/quality-trend", summary="质量趋势")
async def get_quality_trend(limit: int = Query(20, ge=1, le=120)):
    return {"items": _load_baselines(limit=limit)}


@router.get("/cost-estimate", summary="成本估算")
async def get_cost_estimate(case_count: int = Query(100, ge=1, le=5000)):
    return estimate_cost(case_count=case_count)


@router.post("/feedback", summary="提交分析反馈")
async def submit_feedback(payload: FeedbackRequest):
    return await feedback_service.append(payload.model_dump(mode="json"))


@router.get("/feedback", summary="查看反馈记录")
async def list_feedback(limit: int = Query(50, ge=1, le=500)):
    items = await feedback_service.list(limit=limit)
    return {"items": items}


@router.get("/feedback/learning-candidates", summary="反馈学习候选")
async def feedback_learning_candidates(limit: int = Query(200, ge=1, le=2000)):
    rows = await feedback_service.list(limit=limit)
    counters: Dict[str, int] = {"adopt": 0, "reject": 0, "revise": 0}
    tags: Dict[str, int] = {}
    for row in rows:
        verdict = str(row.get("verdict") or "")
        if verdict in counters:
            counters[verdict] += 1
        for tag in (row.get("tags") or []):
            text = str(tag).strip()
            if not text:
                continue
            tags[text] = tags.get(text, 0) + 1
    prompt_candidates = [
        {
            "title": "减少“需要进一步分析”结论",
            "suggestion": "要求 JudgeAgent 输出至少一个可验证证据引用与可执行下一步。",
            "priority": "high",
        },
        {
            "title": "增强跨源证据约束",
            "suggestion": "结论必须同时引用日志与代码/领域/指标证据，否则拒绝收敛。",
            "priority": "high",
        },
    ]
    rule_candidates = [
        {
            "name": "cross_source_required",
            "condition": "root_cause.confidence < 0.65 and evidence_sources < 2",
            "action": "request_more_evidence",
        },
        {
            "name": "timeout_degrade_protection",
            "condition": "agent_timeout_rate > 0.35",
            "action": "reduce_context_and_retry_once",
        },
    ]
    return {
        "summary": counters,
        "top_tags": sorted([{"tag": k, "count": v} for k, v in tags.items()], key=lambda x: x["count"], reverse=True)[:20],
        "prompt_candidates": prompt_candidates,
        "rule_candidates": rule_candidates,
    }


@router.get("/tenants", summary="多租户策略列表")
async def list_tenants():
    items = await governance_ops_service.list_tenants()
    return {"items": items}


@router.put("/tenants", summary="更新多租户策略")
async def upsert_tenant(payload: TenantPolicyRequest):
    item = await governance_ops_service.upsert_tenant(payload.model_dump(mode="json"))
    return item


@router.post("/ab-evaluate", summary="A/B 评测")
async def ab_evaluate(strategy_a: str = "baseline", strategy_b: str = "candidate"):
    return await governance_ops_service.ab_evaluate(strategy_a=strategy_a, strategy_b=strategy_b)


@router.post("/external-sync", summary="外部协同双向同步（桩）")
async def external_sync(payload: ExternalSyncRequest):
    return await governance_ops_service.sync_external(payload.model_dump(mode="json"))


@router.get("/external-sync", summary="外部协同同步记录")
async def list_external_sync(limit: int = Query(100, ge=1, le=1000)):
    items = await governance_ops_service.list_external_sync(limit=limit)
    return {"items": items}


@router.get("/external-sync/templates", summary="外部协同字段映射模板")
async def external_sync_templates():
    return await governance_ops_service.external_sync_templates()


@router.get("/external-sync/settings", summary="外部协同自动同步设置")
async def external_sync_settings():
    return await governance_ops_service.get_external_sync_settings()


@router.put("/external-sync/settings", summary="更新外部协同自动同步设置")
async def update_external_sync_settings(payload: ExternalSyncSettingsRequest):
    return await governance_ops_service.update_external_sync_settings(payload.model_dump(mode="json"))


@router.get("/runtime-strategies", summary="运行策略模板列表")
async def runtime_strategies():
    return {"items": runtime_strategy_center.list_profiles()}


@router.get("/runtime-strategies/active", summary="当前运行策略")
async def runtime_strategy_active():
    active = runtime_strategy_center.get_active()
    profile = runtime_strategy_center.get_profile(str(active.get("active_profile") or "balanced"))
    return {**active, "profile": profile}


@router.put("/runtime-strategies/active", summary="设置当前运行策略")
async def update_runtime_strategy_active(payload: RuntimeStrategyRequest):
    active = runtime_strategy_center.set_active(payload.profile)
    profile = runtime_strategy_center.get_profile(str(active.get("active_profile") or "balanced"))
    return {**active, "profile": profile}


@router.get("/team-metrics", summary="团队治理指标")
async def team_metrics(
    days: int = Query(7, ge=1, le=90, description="统计时间窗（天）"),
    limit: int = Query(50, ge=1, le=500, description="返回团队条目数"),
):
    return await governance_ops_service.team_metrics(days=days, limit=limit)


@router.get("/session-replay/{session_id}", summary="按 session 回放关键决策路径")
async def session_replay(
    session_id: str,
    limit: int = Query(120, ge=1, le=1000, description="回放步数上限"),
):
    return await governance_ops_service.session_replay(session_id=session_id, limit=limit)


@router.post("/remediation/propose", summary="创建修复提案")
async def remediation_propose(payload: RemediationProposeRequest):
    return await remediation_service.propose(
        incident_id=payload.incident_id,
        session_id=payload.session_id,
        summary=payload.summary,
        steps=list(payload.steps or []),
        risk_level=payload.risk_level,
        pre_slo=dict(payload.pre_slo or {}),
    )


@router.get("/remediation/actions", summary="修复动作列表")
async def remediation_actions(limit: int = Query(100, ge=1, le=500)):
    return {"items": await remediation_service.list_actions(limit=limit)}


@router.get("/remediation/actions/{action_id}", summary="修复动作详情")
async def remediation_action_detail(action_id: str):
    row = await remediation_service.get_action(action_id)
    if not row:
        return {"found": False}
    return {"found": True, "item": row}


@router.post("/remediation/actions/{action_id}/simulate", summary="修复模拟")
async def remediation_simulate(action_id: str, payload: RemediationSimulateRequest):
    return await remediation_service.simulate(action_id, simulated_slo=dict(payload.simulated_slo or {}))


@router.post("/remediation/actions/{action_id}/approve", summary="修复审批")
async def remediation_approve(action_id: str, payload: RemediationApproveRequest):
    return await remediation_service.approve(action_id, approver=payload.approver, comment=payload.comment)


@router.post("/remediation/actions/{action_id}/execute", summary="修复执行")
async def remediation_execute(action_id: str, payload: RemediationExecuteRequest):
    return await remediation_service.execute(
        action_id,
        operator=payload.operator,
        post_slo=dict(payload.post_slo or {}),
    )


@router.post("/remediation/actions/{action_id}/verify", summary="修复验证")
async def remediation_verify(action_id: str, payload: RemediationVerifyRequest):
    return await remediation_service.verify(action_id, verifier=payload.verifier, verification=dict(payload.verification or {}))


@router.post("/remediation/actions/{action_id}/rollback", summary="回滚方案/执行")
async def remediation_rollback(action_id: str, payload: RemediationRollbackRequest):
    return await remediation_service.rollback(action_id, reason=payload.reason, execute=bool(payload.execute))


@router.post("/remediation/actions/{action_id}/change-link", summary="变更联动")
async def remediation_change_link(action_id: str, payload: RemediationChangeLinkRequest):
    return await remediation_service.link_change_window(
        action_id,
        change_id=payload.change_id,
        window=payload.window,
        release_type=payload.release_type,
    )
