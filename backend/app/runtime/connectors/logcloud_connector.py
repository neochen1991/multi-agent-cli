"""Log cloud connector entrypoint (disabled by default)."""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode

from app.models.tooling import LogCloudSourceConfig
from app.runtime.connectors.http_utils import http_get_json


class LogCloudConnector:
    name = "LogCloudConnector"
    resource_type = "logcloud"

    async def fetch(self, config: LogCloudSourceConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        if not bool(config.enabled):
            return {"enabled": False, "status": "disabled", "data": {}, "message": "log cloud source disabled"}
        endpoint = str(config.endpoint or "").strip()
        if not endpoint:
            return {"enabled": True, "status": "unavailable", "data": {}, "message": "endpoint is empty"}

        service_name = str(context.get("service_name") or "").strip()
        trace_id = str(context.get("trace_id") or "").strip()
        query = str(context.get("query") or "").strip()
        query_params = {}
        if service_name:
            query_params["service"] = service_name
        if trace_id:
            query_params["trace_id"] = trace_id
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
                "message": "log cloud fetched",
                "context_hint": {"service_name": service_name, "trace_id": trace_id},
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
                "message": f"log cloud fetch failed: {str(exc)[:180]}",
                "context_hint": {"service_name": service_name, "trace_id": trace_id},
            }


__all__ = ["LogCloudConnector"]

