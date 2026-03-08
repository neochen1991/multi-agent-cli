"""
DDD 分析工具模块

本模块提供领域驱动设计（DDD）元素提取功能。

主要功能：
从文档和代码中提取 DDD 元素：
- Aggregate（聚合）：聚合根定义
- Entity（实体）：实体类定义
- ValueObject（值对象）：值对象定义
- DomainService（领域服务）：领域服务定义
- BoundedContext（限界上下文）：限界上下文定义

使用场景：
该工具由 DomainAgent 使用，用于分析代码和文档中的领域模型，
帮助确定接口到责任田的映射关系。

DDD Analyzer Tool
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.tools.base import BaseTool, ToolResult


class DDDAnalyzerTool(BaseTool):
    """
    DDD 分析工具

    从文档和代码中提取领域驱动设计元素，支持：
    - 聚合（Aggregate）
    - 实体（Entity）
    - 值对象（ValueObject）
    - 领域服务（DomainService）
    - 限界上下文（BoundedContext）

    该工具由 DomainAgent 使用，用于分析接口与责任田的映射关系。
    """

    def __init__(self):
        """初始化 DDD 分析工具"""
        super().__init__(name="ddd_analyzer", description="从文档和代码中提取 DDD 元素")

    async def execute(self, content: str, **kwargs) -> ToolResult:
        """
        执行 DDD 元素提取

        从给定的内容中提取 DDD 元素。

        Args:
            content: 要分析的内容（文档或代码）
            **kwargs: 其他参数

        Returns:
            ToolResult: 包含提取的 DDD 元素列表
        """
        try:
            # 提取各类 DDD 元素
            aggregates = self._extract_by_prefix(content, ["Aggregate", "聚合"])
            entities = self._extract_by_prefix(content, ["Entity", "实体"])
            value_objects = self._extract_by_prefix(content, ["ValueObject", "值对象"])
            domain_services = self._extract_by_prefix(content, ["DomainService", "领域服务"])
            bounded_contexts = self._extract_by_prefix(content, ["BoundedContext", "限界上下文"])

            return self._create_success_result(
                {
                    "aggregates": aggregates,
                    "entities": entities,
                    "value_objects": value_objects,
                    "domain_services": domain_services,
                    "bounded_contexts": bounded_contexts,
                }
            )
        except Exception as e:
            return self._create_error_result(str(e))

    def _extract_by_prefix(self, content: str, prefixes: List[str]) -> List[str]:
        """
        根据前缀提取元素

        从内容中匹配指定前缀后的元素名称。
        支持中英文前缀，如 ["Aggregate", "聚合"]。

        匹配格式示例：
        - Aggregate: Order
        - 聚合：订单聚合
        - Entity: User

        Args:
            content: 内容
            prefixes: 前缀列表（支持中英文）

        Returns:
            List[str]: 提取的元素名称列表（去重、排序）
        """
        found = set()
        for prefix in prefixes:
            # 构建正则：匹配前缀后的元素名称
            pattern = re.compile(rf"{re.escape(prefix)}[\s:：-]*([A-Za-z][\w-]*)")
            for item in pattern.findall(content):
                found.add(item)
        return sorted(found)

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数 JSON Schema

        Returns:
            Dict[str, Any]: 参数 Schema
        """
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
            },
            "required": ["content"],
        }

