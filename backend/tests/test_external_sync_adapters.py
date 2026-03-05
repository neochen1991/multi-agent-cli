"""Tests for external sync dry-run adapters."""

from __future__ import annotations

import pytest

from app.config import settings
from app.runtime_ext.integrations.jira_adapter import JiraAdapter
from app.runtime_ext.integrations.pagerduty_adapter import PagerDutyAdapter
from app.services.governance_ops_service import GovernanceOpsService


def test_jira_adapter_builds_issue_payload() -> None:
    adapter = JiraAdapter()
    built = adapter.build(
        action="create_issue",
        payload={
            "project_key": "OPS",
            "summary": "order-service 502",
            "description": "hikari timeout",
            "labels": ["incident", "rca"],
        },
    )
    assert built.provider == "jira"
    assert built.payload["fields"]["project"]["key"] == "OPS"
    assert built.payload["fields"]["summary"] == "order-service 502"


def test_pagerduty_adapter_builds_trigger_payload() -> None:
    adapter = PagerDutyAdapter()
    built = adapter.build(
        action="create_incident",
        payload={"routing_key": "rk", "summary": "db lock", "severity": "critical"},
    )
    assert built.provider == "pagerduty"
    assert built.payload["routing_key"] == "rk"
    assert built.payload["event_action"] == "trigger"


@pytest.mark.asyncio
async def test_governance_sync_external_includes_adapter_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "LOCAL_STORE_DIR", str(tmp_path), raising=False)
    service = GovernanceOpsService()
    record = await service.sync_external(
        {
            "provider": "jira",
            "direction": "outbound",
            "action": "create_issue",
            "payload": {"project_key": "OPS", "summary": "gateway 502"},
        }
    )
    assert record["provider"] == "jira"
    assert isinstance(record.get("adapter_payload"), dict)
    assert record["adapter_payload"]["dry_run"] is True
    assert "fields" in record["adapter_payload"]["request_payload"]
