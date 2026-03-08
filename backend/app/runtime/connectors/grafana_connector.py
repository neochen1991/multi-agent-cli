"""
Grafana 连接器模块

本模块提供与 Grafana 可视化平台的集成能力。

核心功能：
1. 从 Grafana 获取仪表板数据
2. 支持按服务名、查询语句查询
3. 错误处理和降级响应

查询参数：
- service_name: 服务名称
- query: 查询语句

返回结构：
{
    "enabled": true,
    "status": "ok",
    "data": {...},
    "request_meta": {...},
    "message": "grafana fetched",
    "context_hint": {...}
}

使用场景：
- 获取仪表板快照
- 查询可视化数据

Grafana connector entrypoint (disabled by default).
"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode

from app.models.tooling import GrafanaSourceConfig
from app.runtime.connectors.http_utils import http_get_json


class GrafanaConnector:
    """
    Grafana 连接器

    从 Grafana 可视化平台获取数据。

    属性：
    - name: 连接器名称
    - resource_type: 资源类型

    配置：
    - endpoint: Grafana API 端点
    - api_token: 认证令牌
    - enabled: 是否启用
    - timeout_seconds: 超时时间
    """

    name = "GrafanaConnector"
    resource_type = "grafana"

    async def fetch(self, config: GrafanaSourceConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取 Grafana 数据

        从 Grafana 获取仪表板或面板数据。

        流程：
        1. 检查是否启用
        2. 构建查询 URL
        3. 发送 HTTP 请求
        4. 处理响应或错误

        Args:
            config: Grafana 配置
            context: 查询上下文，包含 service_name、query

        Returns:
            Dict[str, Any]: Grafana 数据或错误信息
        """
        # 检查是否启用
        if not bool(config.enabled):
            return {"enabled": False, "status": "disabled", "data": {}, "message": "grafana source disabled"}

        endpoint = str(config.endpoint or "").strip()
        if not endpoint:
            return {"enabled": True, "status": "unavailable", "data": {}, "message": "endpoint is empty"}

        # 构建查询参数
        service_name = str(context.get("service_name") or "").strip()
        query = str(context.get("query") or "").strip()
        query_params = {}
        if service_name:
            query_params["service"] = service_name
        if query:
            query_params["query"] = query

        # 构建完整 URL
        url = endpoint
        if query_params:
            suffix = urlencode(query_params)
            url = f"{endpoint}{'&' if '?' in endpoint else '?'}{suffix}"

        try:
            # 发送请求
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
                "message": "grafana fetched",
                "context_hint": {"service_name": service_name},
            }
        except Exception as exc:
            # 错误处理
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
                "message": f"grafana fetch failed: {str(exc)[:180]}",
                "context_hint": {"service_name": service_name},
            }


__all__ = ["GrafanaConnector"]