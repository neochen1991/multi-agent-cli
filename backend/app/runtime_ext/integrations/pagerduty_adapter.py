"""PagerDuty dry-run adapter."""

from __future__ import annotations

from typing import Any, Dict

from app.runtime_ext.integrations.base_adapter import AdapterBuildResult


class PagerDutyAdapter:
    """封装PagerDutyAdapter相关数据结构或服务能力。"""
    provider = "pagerduty"

    def build(self, *, action: str, payload: Dict[str, Any]) -> AdapterBuildResult:
        """构建构建，供后续节点或调用方直接使用。"""
        body = {
            "routing_key": str(payload.get("routing_key") or "dry-run"),
            "event_action": "trigger" if action == "create_incident" else str(action or "trigger"),
            "payload": {
                "summary": str(payload.get("summary") or "SRE Incident"),
                "source": str(payload.get("source") or "multi-agent-cli"),
                "severity": str(payload.get("severity") or "error"),
                "custom_details": dict(payload.get("custom_details") or {}),
            },
        }
        return AdapterBuildResult(provider=self.provider, action=action, payload=body, dry_run=True)


__all__ = ["PagerDutyAdapter"]

