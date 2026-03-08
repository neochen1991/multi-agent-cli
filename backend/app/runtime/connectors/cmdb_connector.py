"""
CMDB 连接器模块

本模块提供与 CMDB（配置管理数据库）系统的集成能力。

核心功能：
1. 从 CMDB 获取配置项数据
2. 支持按服务名查询
3. 错误处理和降级响应

查询参数：
- service_name: 服务名称

返回结构：
{
    "enabled": true,
    "status": "ok",
    "data": {...},
    "request_meta": {...},
    "message": "cmdb fetched",
    "context_hint": {...}
}

使用场景：
- 获取服务配置信息
- 查询资产清单
- 服务依赖关系分析

CMDB connector entrypoint (disabled by default).
"""

from __future__ import annotations

from typing import Any, Dict

from app.models.tooling import CMDBSourceConfig
from app.runtime.connectors.http_utils import http_get_json


class CMDBConnector:
    """
    CMDB 连接器

    从 CMDB 系统获取配置项数据。

    属性：
    - name: 连接器名称
    - resource_type: 资源类型

    配置：
    - endpoint: CMDB API 端点
    - api_token: 认证令牌
    - enabled: 是否启用
    - timeout_seconds: 超时时间
    """

    name = "CMDBConnector"
    resource_type = "cmdb"

    async def fetch(self, config: CMDBSourceConfig, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取配置项数据

        从 CMDB 获取配置项数据。

        流程：
        1. 检查是否启用
        2. 发送 HTTP 请求
        3. 处理响应或错误

        Args:
            config: CMDB 配置
            context: 查询上下文，包含 service_name

        Returns:
            Dict[str, Any]: 配置项数据或错误信息
        """
        # 检查是否启用
        if not bool(config.enabled):
            return {"enabled": False, "status": "disabled", "data": {}, "message": "cmdb source disabled"}

        endpoint = str(config.endpoint or "").strip()
        if not endpoint:
            return {"enabled": True, "status": "unavailable", "data": {}, "message": "endpoint is empty"}

        try:
            # 发送请求
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
                "message": "cmdb fetched",
                "context_hint": {"service_name": str(context.get("service_name") or "")},
            }
        except Exception as exc:
            # 错误处理
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
                "message": f"cmdb fetch failed: {str(exc)[:180]}",
                "context_hint": {"service_name": str(context.get("service_name") or "")},
            }