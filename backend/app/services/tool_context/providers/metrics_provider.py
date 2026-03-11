"""Metrics tool-context provider."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.tooling import AgentToolingConfig
from app.services.tool_context.result import ToolContextResult


async def build_metrics_context(
    service: Any,
    *,
    cfg: AgentToolingConfig,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    assigned_command: Optional[Dict[str, Any]],
    command_gate: Dict[str, Any],
) -> ToolContextResult:
    """Build MetricsAgent tool context from telemetry/APM/metric sources."""
    audit_log: List[Dict[str, Any]] = [
        service._audit(  # noqa: SLF001
            tool_name="metrics_snapshot_analyzer",
            action="command_gate",
            status="ok" if command_gate.get("allow_tool") else "skipped",
            detail={
                "reason": str(command_gate.get("reason") or ""),
                "has_command": bool(command_gate.get("has_command")),
                "decision_source": str(command_gate.get("decision_source") or ""),
                "command_preview": service._command_preview(assigned_command),  # noqa: SLF001
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
            data={"command_preview": service._command_preview(assigned_command)},  # noqa: SLF001
            command_gate=command_gate,
            audit_log=audit_log,
        )

    remote_telemetry_payload: Dict[str, Any] = {}
    remote_prometheus_payload: Dict[str, Any] = {}
    remote_loki_payload: Dict[str, Any] = {}
    remote_grafana_payload: Dict[str, Any] = {}
    remote_apm_payload: Dict[str, Any] = {}
    service_name = service._primary_service_name(compact_context, incident_context, assigned_command)  # noqa: SLF001
    trace_id = service._primary_trace_id(compact_context, incident_context, assigned_command)  # noqa: SLF001

    if bool(cfg.telemetry_source.enabled):
        telemetry_result = await service._telemetry_connector.fetch(  # noqa: SLF001
            cfg.telemetry_source,
            {"service_name": service_name, "trace_id": trace_id},
        )
        telemetry_status = str(telemetry_result.get("status") or "unknown")
        telemetry_request_meta = dict(telemetry_result.get("request_meta") or {})
        audit_log.append(
            service._audit(  # noqa: SLF001
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
        prometheus_result = await service._prometheus_connector.fetch(  # noqa: SLF001
            cfg.prometheus_source,
            {
                "service_name": service_name,
                "query": str(assigned_command.get("focus") if isinstance(assigned_command, dict) else ""),
            },
        )
        prometheus_status = str(prometheus_result.get("status") or "unknown")
        prometheus_request_meta = dict(prometheus_result.get("request_meta") or {})
        audit_log.append(
            service._audit(  # noqa: SLF001
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
        loki_result = await service._loki_connector.fetch(  # noqa: SLF001
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
            service._audit(  # noqa: SLF001
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
        grafana_result = await service._grafana_connector.fetch(  # noqa: SLF001
            cfg.grafana_source,
            {
                "service_name": service_name,
                "query": str(assigned_command.get("focus") if isinstance(assigned_command, dict) else ""),
            },
        )
        grafana_status = str(grafana_result.get("status") or "unknown")
        grafana_request_meta = dict(grafana_result.get("request_meta") or {})
        audit_log.append(
            service._audit(  # noqa: SLF001
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
        apm_result = await service._apm_connector.fetch(  # noqa: SLF001
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
            service._audit(  # noqa: SLF001
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
    signals = service._collect_metrics_signals(compact_context, metrics_context)  # noqa: SLF001
    audit_log.append(
        service._audit(  # noqa: SLF001
            tool_name="metrics_snapshot_analyzer",
            action="metrics_extract",
            status="ok" if signals else "unavailable",
            detail={"signal_count": len(signals), "sources": ["compact_context", "incident_context", "log_content"]},
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
