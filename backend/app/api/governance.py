"""治理中心 API。

统一对外暴露系统卡、质量趋势、反馈学习、运行策略、部署图配置、人工审核队列和修复提案等治理能力。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.governance.system_card import build_system_card, estimate_cost
from app.runtime.langgraph.deployment_center import deployment_center
from app.runtime.langgraph.strategy_center import runtime_strategy_center
from app.runtime.task_registry import runtime_task_registry
from app.core.task_queue import task_queue
from app.config import settings
from app.models.incident import IncidentStatus, IncidentUpdate
from app.services.incident_service import incident_service
from app.services.debate_service import HumanReviewRequired, debate_service
from app.services.feedback_service import feedback_service
from app.services.governance_ops_service import governance_ops_service
from app.services.remediation_service import remediation_service

router = APIRouter()


class FeedbackRequest(BaseModel):
    """分析结果反馈请求。"""

    incident_id: str = Field(default="")
    session_id: str = Field(default="")
    verdict: str = Field(default="adopt", pattern="^(adopt|reject|revise)$")
    comment: str = Field(default="")
    tags: list[str] = Field(default_factory=list)


class RemediationProposeRequest(BaseModel):
    """创建修复提案时的请求体。"""

    incident_id: str
    session_id: str
    summary: str
    steps: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="medium")
    pre_slo: Dict[str, Any] = Field(default_factory=dict)


class RemediationSimulateRequest(BaseModel):
    """修复模拟时附带的目标/模拟 SLO。"""

    simulated_slo: Dict[str, Any] = Field(default_factory=dict)


class RemediationApproveRequest(BaseModel):
    """修复提案审批请求。"""

    approver: str = Field(default="sre-oncall")
    comment: str = Field(default="")


class RemediationExecuteRequest(BaseModel):
    """执行修复动作时的操作人和执行后观测指标。"""

    operator: str = Field(default="sre-oncall")
    post_slo: Dict[str, Any] = Field(default_factory=dict)


class RemediationVerifyRequest(BaseModel):
    """修复验证请求。"""

    verifier: str = Field(default="qa")
    verification: Dict[str, Any] = Field(default_factory=dict)


class RemediationRollbackRequest(BaseModel):
    """回滚请求，可只生成方案，也可直接执行。"""

    reason: str = Field(default="")
    execute: bool = Field(default=False)


class RemediationChangeLinkRequest(BaseModel):
    """修复动作与变更窗口联动请求。"""

    change_id: str
    window: str = Field(default="business-hours")
    release_type: str = Field(default="app")


class TenantPolicyRequest(BaseModel):
    """多租户治理策略更新请求。"""

    tenant_id: str
    name: str = Field(default="")
    rbac: Dict[str, Any] = Field(default_factory=dict)
    quota: Dict[str, Any] = Field(default_factory=dict)
    budget: Dict[str, Any] = Field(default_factory=dict)
    isolation: Dict[str, Any] = Field(default_factory=dict)


class ExternalSyncRequest(BaseModel):
    """外部系统同步请求。"""

    provider: str = Field(pattern="^(jira|servicenow|slack|feishu|pagerduty)$")
    direction: str = Field(default="outbound", pattern="^(outbound|inbound)$")
    action: str = Field(default="notify")
    payload: Dict[str, Any] = Field(default_factory=dict)


class ExternalSyncSettingsRequest(BaseModel):
    """外部协同自动同步开关与可用 provider 配置。"""

    enabled: bool = Field(default=False)
    providers: List[str] = Field(default_factory=list)


class RuntimeStrategyRequest(BaseModel):
    """切换运行策略时的请求体。"""

    profile: str = Field(default="balanced")


class DeploymentProfileRequest(BaseModel):
    """切换部署图模板时的请求体。"""

    profile: str = Field(default="skill_enabled")


class HumanReviewApproveRequest(BaseModel):
    """人工审核批准请求。"""

    approver: str = Field(default="sre-oncall")
    comment: str = Field(default="")


class HumanReviewRejectRequest(BaseModel):
    """人工审核驳回请求。"""

    approver: str = Field(default="sre-oncall")
    reason: str = Field(default="")


class HumanReviewResumeRequest(BaseModel):
    """人工审核通过后恢复执行请求。"""

    operator: str = Field(default="sre-oncall")


def _metrics_dir() -> Path:
    """定位治理页读取基线趋势文件的目录。"""
    return Path(__file__).resolve().parents[3] / "docs" / "metrics"


def _load_baselines(limit: int = 20) -> List[Dict[str, Any]]:
    """读取最近的 benchmark 基线文件，供质量趋势和治理首页展示使用。"""
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
    """返回系统边界卡，说明平台能力、门禁和硬约束。"""
    return build_system_card()


@router.get("/quality-trend", summary="质量趋势")
async def get_quality_trend(limit: int = Query(20, ge=1, le=120)):
    """返回质量趋势所需的历史基线文件摘要。"""
    return {"items": _load_baselines(limit=limit)}


@router.get("/cost-estimate", summary="成本估算")
async def get_cost_estimate(case_count: int = Query(100, ge=1, le=5000)):
    """估算指定案例规模下的粗略成本。"""
    return estimate_cost(case_count=case_count)


@router.post("/feedback", summary="提交分析反馈")
async def submit_feedback(payload: FeedbackRequest):
    """追加一条分析反馈，用于后续反馈学习。"""
    return await feedback_service.append(payload.model_dump(mode="json"))


@router.get("/feedback", summary="查看反馈记录")
async def list_feedback(limit: int = Query(50, ge=1, le=500)):
    """查看反馈记录列表。"""
    items = await feedback_service.list(limit=limit)
    return {"items": items}


@router.get("/feedback/learning-candidates", summary="反馈学习候选")
async def feedback_learning_candidates(limit: int = Query(200, ge=1, le=2000)):
    """根据反馈记录生成 prompt/rule 的改进候选。"""
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
    """列出多租户治理策略。"""
    items = await governance_ops_service.list_tenants()
    return {"items": items}


@router.put("/tenants", summary="更新多租户策略")
async def upsert_tenant(payload: TenantPolicyRequest):
    """新增或更新单个租户的治理策略。"""
    item = await governance_ops_service.upsert_tenant(payload.model_dump(mode="json"))
    return item


@router.post("/ab-evaluate", summary="A/B 评测")
async def ab_evaluate(strategy_a: str = "baseline", strategy_b: str = "candidate"):
    """执行两个策略模板的 A/B 对比评估。"""
    return await governance_ops_service.ab_evaluate(strategy_a=strategy_a, strategy_b=strategy_b)


@router.post("/external-sync", summary="外部协同双向同步（桩）")
async def external_sync(payload: ExternalSyncRequest):
    """触发一次外部系统同步。"""
    return await governance_ops_service.sync_external(payload.model_dump(mode="json"))


@router.get("/external-sync", summary="外部协同同步记录")
async def list_external_sync(limit: int = Query(100, ge=1, le=1000)):
    """查看外部同步历史记录。"""
    items = await governance_ops_service.list_external_sync(limit=limit)
    return {"items": items}


@router.get("/external-sync/templates", summary="外部协同字段映射模板")
async def external_sync_templates():
    """返回外部同步字段映射模板。"""
    return await governance_ops_service.external_sync_templates()


@router.get("/external-sync/settings", summary="外部协同自动同步设置")
async def external_sync_settings():
    """读取外部自动同步设置。"""
    return await governance_ops_service.get_external_sync_settings()


@router.put("/external-sync/settings", summary="更新外部协同自动同步设置")
async def update_external_sync_settings(payload: ExternalSyncSettingsRequest):
    """更新外部自动同步开关与 provider 列表。"""
    return await governance_ops_service.update_external_sync_settings(payload.model_dump(mode="json"))


@router.get("/runtime-strategies", summary="运行策略模板列表")
async def runtime_strategies():
    """列出全部运行策略模板。"""
    return {"items": runtime_strategy_center.list_profiles()}


@router.get("/runtime-strategies/active", summary="当前运行策略")
async def runtime_strategy_active():
    """读取当前激活的运行策略及其配置详情。"""
    active = runtime_strategy_center.get_active()
    profile = runtime_strategy_center.get_profile(str(active.get("active_profile") or "balanced"))
    return {**active, "profile": profile}


@router.put("/runtime-strategies/active", summary="设置当前运行策略")
async def update_runtime_strategy_active(payload: RuntimeStrategyRequest):
    """切换当前运行策略模板。"""
    active = runtime_strategy_center.set_active(payload.profile)
    profile = runtime_strategy_center.get_profile(str(active.get("active_profile") or "balanced"))
    return {**active, "profile": profile}


@router.get("/deployment-profiles", summary="部署图模板列表")
async def deployment_profiles():
    """列出全部部署图模板。"""
    return {"items": deployment_center.list_profiles()}


@router.get("/deployment-profiles/active", summary="当前部署图模板")
async def deployment_profile_active():
    """读取当前激活的部署图模板。"""
    active = deployment_center.get_active()
    profile = deployment_center.get_profile(str(active.get("active_profile") or "skill_enabled"))
    return {**active, "profile": profile}


@router.put("/deployment-profiles/active", summary="设置当前部署图模板")
async def update_deployment_profile_active(payload: DeploymentProfileRequest):
    """切换当前部署图模板。"""
    active = deployment_center.set_active(payload.profile)
    profile = deployment_center.get_profile(str(active.get("active_profile") or "skill_enabled"))
    return {**active, "profile": profile}


@router.get("/human-review", summary="待人工审核会话列表")
async def list_human_review(limit: int = Query(50, ge=1, le=500)):
    """列出人工审核队列，并附带待处理/已批准数量摘要。"""
    items = await governance_ops_service.list_human_reviews(limit=limit)
    summary = {
        "pending": sum(1 for item in items if str(item.get("review_status") or "") == "pending"),
        "approved": sum(1 for item in items if str(item.get("review_status") or "") == "approved"),
    }
    return {"items": items, "summary": summary}


@router.post("/human-review/{session_id}/approve", summary="治理中心批准人工审核")
async def approve_human_review(session_id: str, payload: HumanReviewApproveRequest):
    """在治理中心批准某个待审核会话。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )
    approved = await debate_service.approve_human_review(
        session_id,
        approver=payload.approver,
        comment=payload.comment,
    )
    if not approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no pending human review to approve",
        )
    await runtime_task_registry.mark_review_decision(
        session_id,
        review_status="approved",
        status="waiting_review",
    )
    return {"session_id": session_id, "success": True, "review_status": "approved"}


@router.post("/human-review/{session_id}/reject", summary="治理中心驳回人工审核")
async def reject_human_review(session_id: str, payload: HumanReviewRejectRequest):
    """在治理中心驳回某个待审核会话，并同步关闭 incident。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )
    rejected = await debate_service.reject_human_review(
        session_id,
        approver=payload.approver,
        reason=payload.reason,
    )
    if not rejected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no pending human review to reject",
        )
    await runtime_task_registry.mark_review_decision(
        session_id,
        review_status="rejected",
        status="failed",
        error="human_review_rejected",
    )
    await incident_service.update_incident(
        session.incident_id,
        IncidentUpdate(
            status=IncidentStatus.CLOSED,
            fix_suggestion=payload.reason or "human_review_rejected",
        ),
    )
    return {"session_id": session_id, "success": True, "review_status": "rejected"}


@router.post("/human-review/{session_id}/resume", summary="治理中心恢复已批准会话")
async def resume_human_review(session_id: str, payload: HumanReviewResumeRequest):
    """恢复一个已批准且等待继续执行的会话。"""
    session = await debate_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {session_id} not found",
        )
    review = (session.context or {}).get("human_review")
    review_status = str(review.get("status") or "").strip().lower() if isinstance(review, dict) else ""
    session_status = str(getattr(session.status, "value", session.status) or "").strip().lower()
    if session_status != "waiting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="session is not waiting for human review resume",
        )
    if review_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="human review is not approved",
        )

    context = dict(session.context or {})
    context["execution_mode"] = "background"
    session.context = context
    await debate_service.update_session(session)
    await incident_service.update_incident(
        session.incident_id,
        IncidentUpdate(status=IncidentStatus.ANALYZING),
    )

    async def _run():
        """后台恢复执行任务，负责更新运行时状态和 incident 最终结果。"""
        try:
            await runtime_task_registry.mark_started(
                session_id=session_id,
                task_type="debate",
                trace_id=str((session.context or {}).get("trace_id") or ""),
            )
            result = await debate_service.execute_debate(session_id)
            await runtime_task_registry.mark_done(session_id, status="completed")
            await incident_service.update_incident(
                session.incident_id,
                IncidentUpdate(
                    status=IncidentStatus.RESOLVED,
                    root_cause=result.root_cause,
                    fix_suggestion=(result.fix_recommendation.summary if result.fix_recommendation else None),
                    impact_analysis=(result.impact_analysis.model_dump() if result.impact_analysis else None),
                ),
            )
            return {
                "session_id": result.session_id,
                "incident_id": result.incident_id,
                "confidence": result.confidence,
            }
        except HumanReviewRequired as exc:
            await runtime_task_registry.mark_waiting_review(
                session_id,
                review_reason=exc.reason,
                resume_from_step=exc.resume_from_step,
                phase="waiting_review",
                event_type="human_review_requested",
            )
            return {
                "session_id": session_id,
                "status": "waiting_review",
                "review_status": "pending",
                "review_reason": exc.reason,
                "resume_from_step": exc.resume_from_step,
            }
        except Exception as exc:
            await runtime_task_registry.mark_done(session_id, status="failed", error=str(exc))
            await incident_service.update_incident(
                session.incident_id,
                IncidentUpdate(
                    status=IncidentStatus.CLOSED,
                    fix_suggestion=str(exc)[:260],
                ),
            )
            raise

    task_id = task_queue.submit(_run, timeout_seconds=max(60, int(settings.DEBATE_TIMEOUT or 600)))
    return {"session_id": session_id, "task_id": task_id, "status": "pending", "operator": payload.operator}


@router.get("/team-metrics", summary="团队治理指标")
async def team_metrics(
    days: int = Query(7, ge=1, le=90, description="统计时间窗（天）"),
    limit: int = Query(50, ge=1, le=500, description="返回团队条目数"),
):
    """返回按团队聚合的治理指标。"""
    return await governance_ops_service.team_metrics(days=days, limit=limit)


@router.get("/session-replay/{session_id}", summary="按 session 回放关键决策路径")
async def session_replay(
    session_id: str,
    limit: int = Query(120, ge=1, le=1000, description="回放步数上限"),
):
    """回放指定 session 的关键决策路径。"""
    return await governance_ops_service.session_replay(session_id=session_id, limit=limit)


@router.post("/remediation/propose", summary="创建修复提案")
async def remediation_propose(payload: RemediationProposeRequest):
    """创建修复提案。"""
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
    """列出修复动作列表。"""
    return {"items": await remediation_service.list_actions(limit=limit)}


@router.get("/remediation/actions/{action_id}", summary="修复动作详情")
async def remediation_action_detail(action_id: str):
    """读取单个修复动作详情。"""
    row = await remediation_service.get_action(action_id)
    if not row:
        return {"found": False}
    return {"found": True, "item": row}


@router.post("/remediation/actions/{action_id}/simulate", summary="修复模拟")
async def remediation_simulate(action_id: str, payload: RemediationSimulateRequest):
    """对修复动作做模拟评估。"""
    return await remediation_service.simulate(action_id, simulated_slo=dict(payload.simulated_slo or {}))


@router.post("/remediation/actions/{action_id}/approve", summary="修复审批")
async def remediation_approve(action_id: str, payload: RemediationApproveRequest):
    """审批修复动作。"""
    return await remediation_service.approve(action_id, approver=payload.approver, comment=payload.comment)


@router.post("/remediation/actions/{action_id}/execute", summary="修复执行")
async def remediation_execute(action_id: str, payload: RemediationExecuteRequest):
    """执行修复动作。"""
    return await remediation_service.execute(
        action_id,
        operator=payload.operator,
        post_slo=dict(payload.post_slo or {}),
    )


@router.post("/remediation/actions/{action_id}/verify", summary="修复验证")
async def remediation_verify(action_id: str, payload: RemediationVerifyRequest):
    """提交修复验证结果。"""
    return await remediation_service.verify(action_id, verifier=payload.verifier, verification=dict(payload.verification or {}))


@router.post("/remediation/actions/{action_id}/rollback", summary="回滚方案/执行")
async def remediation_rollback(action_id: str, payload: RemediationRollbackRequest):
    """生成或执行回滚方案。"""
    return await remediation_service.rollback(action_id, reason=payload.reason, execute=bool(payload.execute))


@router.post("/remediation/actions/{action_id}/change-link", summary="变更联动")
async def remediation_change_link(action_id: str, payload: RemediationChangeLinkRequest):
    """将修复动作与具体变更窗口绑定。"""
    return await remediation_service.link_change_window(
        action_id,
        change_id=payload.change_id,
        window=payload.window,
        release_type=payload.release_type,
    )
