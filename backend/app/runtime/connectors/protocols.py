"""
连接器协议定义模块

本模块定义外部数据源连接器的标准接口。

核心功能：
1. 定义连接器协议接口
2. 统一数据获取方式

协议属性：
- name: 连接器名称
- resource_type: 资源类型

协议方法：
- fetch: 获取资源快照

实现示例：
- LogcloudConnector: 日志平台连接器
- PrometheusConnector: Prometheus 连接器
- GrafanaConnector: Grafana 连接器

Connector protocol definitions.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol


class ConnectorProtocol(Protocol):
    """
    连接器协议

    定义外部数据源连接器的标准接口。

    属性：
    - name: 连接器名称（如 "logcloud", "prometheus"）
    - resource_type: 资源类型（如 "log", "metric"）

    方法：
    - fetch: 获取资源快照，返回数据字典
    """

    name: str  # 连接器名称
    resource_type: str  # 资源类型

    async def fetch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取资源快照

        从外部数据源获取数据。

        Args:
            context: 查询上下文，包含查询参数

        Returns:
            Dict[str, Any]: 获取的数据
        """
        ...