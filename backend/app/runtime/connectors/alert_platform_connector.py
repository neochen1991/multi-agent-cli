"""
告警平台连接器模块

本模块提供与告警平台的集成能力。

核心功能：
1. 从告警平台获取告警数据
2. 支持按服务名、严重程度、告警ID查询
3. 错误处理和降级响应

查询参数：
- service_name: 服务名称
- severity: 严重程度
- alert_id: 告警 ID

返回结构：
{
    "enabled": true,
    "status": "ok",
    "data": {...},
    "request_meta": {...},
    "message": "alert platform fetched",
    "context_hint": {...}
}

使用场景：
- 获取告警详情
- 关联告警与故障分析

Alert platform connector entrypoint (disabled by default).
"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlencode

from app.models.tooling import AlertPlatformSourceConfig
from app.runtime.connectors.http_utils import http_get_json


class AlertPlatformConnector:
    """
    告警平台连接器

    从告警平台获取告警数据。

    属性：
    - name: 连接器名称
    - resource_type: 资源类型

    配置：
    - endpoint: 告警平台 API 端点
    - api_token: 认证令牌
    - enabled: 是否启用
    - timeout_seconds: 超时时间
    """

    name = "AlertPlatformConnector"
    resource_type = "alert_platform"

    async def fetch(self, config: AlertPlatformSourceConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取告警数据

        从告警平台获取告警数据。

        流程：
        1. 检查是否启用
        2. 构建查询 URL
        3. 发送 HTTP 请求
        4. 处理响应或错误

        Args:
            config: 告警平台配置
            context: 查询上下文，包含 service_name、severity、alert_id

        Returns:
            Dict[str, Any]: 告警数据或错误信息
        """
        # 检查是否启用
        if not bool(config.enabled):
            return {"enabled": False, "status": "disabled", "data": {}, "message": "alert platform source disabled"}

        endpoint = str(config.endpoint or "").strip()
        if not endpoint:
            return {"enabled": True, "status": "unavailable", "data": {}, "message": "endpoint is empty"}

        # 构建查询参数
        service_name = str(context.get("service_name") or "").strip()
        severity = str(context.get("severity") or "").strip()
        alert_id = str(context.get("alarm_id") or context.get("alert_id") or "").strip()
        query_params = {}
        if service_name:
            query_params["service"] = service_name
        if severity:
            query_params["severity"] = severity
        if alert_id:
            query_params["alert_id"] = alert_id

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
                "message": "alert platform fetched",
                "context_hint": {"service_name": service_name, "alert_id": alert_id},
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
                "message": f"alert platform fetch failed: {str(exc)[:180]}",
                "context_hint": {"service_name": service_name, "alert_id": alert_id},
            }


__all__ = ["AlertPlatformConnector"]