"""
Loki 连接器模块

本模块提供与 Grafana Loki 日志系统的集成能力。

核心功能：
1. 从 Loki 获取日志数据
2. 支持按服务名、追踪ID、查询语句查询
3. 错误处理和降级响应

查询参数：
- service_name: 服务名称
- trace_id: 链路追踪 ID
- query: LogQL 查询语句

返回结构：
{
    "enabled": true,
    "status": "ok",
    "data": {...},
    "request_meta": {...},
    "message": "loki fetched",
    "context_hint": {...}
}

使用场景：
- LogAgent 获取日志数据
- 故障分析时查询相关日志

Loki connector entrypoint (disabled by default).
"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode

from app.models.tooling import LokiSourceConfig
from app.runtime.connectors.http_utils import http_get_json


class LokiConnector:
    """
    Loki 连接器

    从 Grafana Loki 日志系统获取日志数据。

    属性：
    - name: 连接器名称
    - resource_type: 资源类型

    配置：
    - endpoint: Loki API 端点
    - api_token: 认证令牌
    - enabled: 是否启用
    - timeout_seconds: 超时时间
    """

    name = "LokiConnector"
    resource_type = "loki"

    async def fetch(self, config: LokiSourceConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取日志数据

        从 Loki 获取日志数据。

        流程：
        1. 检查是否启用
        2. 构建查询 URL
        3. 发送 HTTP 请求
        4. 处理响应或错误

        Args:
            config: Loki 配置
            context: 查询上下文，包含 service_name、trace_id、query

        Returns:
            Dict[str, Any]: 日志数据或错误信息
        """
        # 检查是否启用
        if not bool(config.enabled):
            return {"enabled": False, "status": "disabled", "data": {}, "message": "loki source disabled"}

        endpoint = str(config.endpoint or "").strip()
        if not endpoint:
            return {"enabled": True, "status": "unavailable", "data": {}, "message": "endpoint is empty"}

        # 构建查询参数
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
                "message": "loki fetched",
                "context_hint": {"service_name": service_name, "trace_id": trace_id},
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
                "message": f"loki fetch failed: {str(exc)[:180]}",
                "context_hint": {"service_name": service_name, "trace_id": trace_id},
            }


__all__ = ["LokiConnector"]