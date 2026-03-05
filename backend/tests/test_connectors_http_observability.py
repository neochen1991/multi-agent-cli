"""Connector observability and degraded-mode tests."""

from __future__ import annotations

import pytest

from app.models.tooling import (
    APMSourceConfig,
    AlertPlatformSourceConfig,
    CMDBSourceConfig,
    GrafanaSourceConfig,
    LogCloudSourceConfig,
    TelemetrySourceConfig,
)
from app.runtime.connectors.apm_connector import APMConnector
from app.runtime.connectors.alert_platform_connector import AlertPlatformConnector
from app.runtime.connectors.cmdb_connector import CMDBConnector
from app.runtime.connectors.grafana_connector import GrafanaConnector
from app.runtime.connectors.logcloud_connector import LogCloudConnector
from app.runtime.connectors.telemetry_connector import TelemetryConnector


@pytest.mark.asyncio
async def test_telemetry_connector_includes_request_meta(monkeypatch):
    async def _fake_http_get_json(**kwargs):  # noqa: ANN003
        assert kwargs.get("include_meta") is True
        return {
            "data": {"cpu": 0.91},
            "request_meta": {
                "url": kwargs.get("url"),
                "method": "GET",
                "status_code": 200,
                "latency_ms": 12.3,
                "retry_count": 0,
                "status": "ok",
            },
        }

    monkeypatch.setattr(
        "app.runtime.connectors.telemetry_connector.http_get_json",
        _fake_http_get_json,
    )

    connector = TelemetryConnector()
    cfg = TelemetrySourceConfig(enabled=True, endpoint="http://example.com/telemetry", api_token="", timeout_seconds=5)
    payload = await connector.fetch(cfg, {"service_name": "order-service"})

    assert payload["status"] == "ok"
    assert payload["data"]["cpu"] == 0.91
    assert payload["request_meta"]["status_code"] == 200
    assert payload["request_meta"]["latency_ms"] == 12.3


@pytest.mark.asyncio
async def test_cmdb_connector_returns_degraded_on_http_error(monkeypatch):
    async def _fake_http_get_json(**kwargs):  # noqa: ANN003
        raise RuntimeError("http_error:503")

    monkeypatch.setattr(
        "app.runtime.connectors.cmdb_connector.http_get_json",
        _fake_http_get_json,
    )

    connector = CMDBConnector()
    cfg = CMDBSourceConfig(enabled=True, endpoint="http://example.com/cmdb", api_token="", timeout_seconds=5)
    payload = await connector.fetch(cfg, {"service_name": "order-service"})

    assert payload["status"] == "degraded"
    assert payload["data"] == {}
    assert payload["request_meta"]["status"] == "error"
    assert "http_error:503" in str(payload["request_meta"]["error"])


@pytest.mark.asyncio
async def test_new_platform_connectors_disabled_by_default():
    grafana = await GrafanaConnector().fetch(GrafanaSourceConfig(enabled=False), {})
    apm = await APMConnector().fetch(APMSourceConfig(enabled=False), {})
    logcloud = await LogCloudConnector().fetch(LogCloudSourceConfig(enabled=False), {})
    alert = await AlertPlatformConnector().fetch(AlertPlatformSourceConfig(enabled=False), {})

    assert grafana["status"] == "disabled"
    assert apm["status"] == "disabled"
    assert logcloud["status"] == "disabled"
    assert alert["status"] == "disabled"
