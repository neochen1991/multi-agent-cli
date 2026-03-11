"""Rule suggestion toolkit provider."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.tooling import AgentToolingConfig
from app.services.tool_context.result import ToolContextResult


async def build_rule_suggestion_context(
    service: Any,
    *,
    cfg: AgentToolingConfig,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    assigned_command: Optional[Dict[str, Any]],
    command_gate: Dict[str, Any],
) -> ToolContextResult:
    """Build rule suggestion toolkit from metrics, runbook, and alert sources."""
    metrics = await service._build_metrics_context(  # noqa: SLF001
        cfg=cfg,
        compact_context=compact_context,
        incident_context=incident_context,
        assigned_command=assigned_command,
        command_gate=command_gate,
    )
    runbook = await service._build_runbook_context(  # noqa: SLF001
        compact_context=compact_context,
        incident_context=incident_context,
        assigned_command=assigned_command,
        command_gate=command_gate,
    )
    alert_payload: Dict[str, Any] = {}
    alert_audit_log: List[Dict[str, Any]] = []
    if bool(getattr(cfg, "alert_platform_source", None) and cfg.alert_platform_source.enabled):
        alert_result = await service._alert_platform_connector.fetch(  # noqa: SLF001
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
            service._audit(  # noqa: SLF001
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
