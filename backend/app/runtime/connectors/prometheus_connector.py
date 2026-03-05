"""Prometheus connector entrypoint (disabled by default)."""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode

from app.models.tooling import PrometheusSourceConfig
from app.runtime.connectors.http_utils import http_get_json


class PrometheusConnector:
    name = "PrometheusConnector"
    resource_type = "prometheus"

    async def fetch(self, config: PrometheusSourceConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        if not bool(config.enabled):
            return {"enabled": False, "status": "disabled", "data": {}, "message": "prometheus source disabled"}
        endpoint = str(config.endpoint or "").strip()
        if not endpoint:
            return {"enabled": True, "status": "unavailable", "data": {}, "message": "endpoint is empty"}

        service_name = str(context.get("service_name") or "").strip()
        query = str(context.get("query") or "").strip()
        query_params = {}
        if service_name:
            query_params["service"] = service_name
        if query:
            query_params["query"] = query
        url = endpoint
        if query_params:
            suffix = urlencode(query_params)
            url = f"{endpoint}{'&' if '?' in endpoint else '?'}{suffix}"

        try:
            payload = await http_get_json(
                url=url,
                token=str(config.api_token or ""),
                timeout_seconds=int(config.timeout_seconds or 8),
                include_meta=True,
            )
            return {
                "enabled": True,
                "status": "ok",
                "data": dict(payload.get("data") or {}),
                "request_meta": dict(payload.get("request_meta") or {}),
                "message": "prometheus fetched",
                "context_hint": {"service_name": service_name},
            }
        except Exception as exc:
            return {
                "enabled": True,
                "status": "degraded",
                "data": {},
                "request_meta": {
                    "url": url,
                    "method": "GET",
                    "status": "error",
                    "error": str(exc)[:240],
                },
                "message": f"prometheus fetch failed: {str(exc)[:180]}",
                "context_hint": {"service_name": service_name},
            }


__all__ = ["PrometheusConnector"]
