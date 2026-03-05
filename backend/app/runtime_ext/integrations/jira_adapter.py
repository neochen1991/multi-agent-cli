"""Jira dry-run adapter."""

from __future__ import annotations

from typing import Any, Dict

from app.runtime_ext.integrations.base_adapter import AdapterBuildResult


class JiraAdapter:
    provider = "jira"

    def build(self, *, action: str, payload: Dict[str, Any]) -> AdapterBuildResult:
        body = {
            "fields": {
                "project": {"key": str(payload.get("project_key") or "SRE")},
                "summary": str(payload.get("summary") or "SRE Incident Sync"),
                "description": str(payload.get("description") or ""),
                "issuetype": {"name": str(payload.get("issue_type") or "Incident")},
                "labels": list(payload.get("labels") or []),
            }
        }
        return AdapterBuildResult(provider=self.provider, action=action, payload=body, dry_run=True)


__all__ = ["JiraAdapter"]

