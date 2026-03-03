"""Telemetry connector entrypoint (disabled by default)."""

from __future__ import annotations

from typing import Any, Dict

from app.models.tooling import TelemetrySourceConfig
from app.runtime.connectors.http_utils import http_get_json


class TelemetryConnector:
    name = "TelemetryConnector"
    resource_type = "telemetry"

    async def fetch(self, config: TelemetrySourceConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        if not bool(config.enabled):
            return {"enabled": False, "status": "disabled", "data": {}, "message": "telemetry source disabled"}
        endpoint = str(config.endpoint or "").strip()
        if not endpoint:
            return {"enabled": True, "status": "unavailable", "data": {}, "message": "endpoint is empty"}
        payload = await http_get_json(
            url=endpoint,
            token=str(config.api_token or ""),
            timeout_seconds=int(config.timeout_seconds or 8),
        )
        return {
            "enabled": True,
            "status": "ok",
            "data": payload,
            "message": "telemetry fetched",
            "context_hint": {"service_name": str(context.get("service_name") or "")},
        }

