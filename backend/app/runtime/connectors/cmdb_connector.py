"""CMDB connector entrypoint (disabled by default)."""

from __future__ import annotations

from typing import Any, Dict

from app.models.tooling import CMDBSourceConfig
from app.runtime.connectors.http_utils import http_get_json


class CMDBConnector:
    name = "CMDBConnector"
    resource_type = "cmdb"

    async def fetch(self, config: CMDBSourceConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        if not bool(config.enabled):
            return {"enabled": False, "status": "disabled", "data": {}, "message": "cmdb source disabled"}
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
            "message": "cmdb fetched",
            "context_hint": {"service_name": str(context.get("service_name") or "")},
        }

