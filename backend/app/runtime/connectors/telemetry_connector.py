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
        try:
            payload = await http_get_json(
                url=endpoint,
                token=str(config.api_token or ""),
                timeout_seconds=int(config.timeout_seconds or 8),
                include_meta=True,
            )
            return {
                "enabled": True,
                "status": "ok",
                "data": dict(payload.get("data") or {}),
                "request_meta": dict(payload.get("request_meta") or {}),
                "message": "telemetry fetched",
                "context_hint": {"service_name": str(context.get("service_name") or "")},
            }
        except Exception as exc:
            return {
                "enabled": True,
                "status": "degraded",
                "data": {},
                "request_meta": {
                    "url": endpoint,
                    "method": "GET",
                    "status": "error",
                    "error": str(exc)[:240],
                },
                "message": f"telemetry fetch failed: {str(exc)[:180]}",
                "context_hint": {"service_name": str(context.get("service_name") or "")},
            }
