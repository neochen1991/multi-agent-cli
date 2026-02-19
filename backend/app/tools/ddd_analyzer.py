"""
DDD 分析工具
DDD Analyzer Tool
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.tools.base import BaseTool, ToolResult


class DDDAnalyzerTool(BaseTool):
    def __init__(self):
        super().__init__(name="ddd_analyzer", description="从文档和代码中提取 DDD 元素")

    async def execute(self, content: str, **kwargs) -> ToolResult:
        try:
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
        found = set()
        for prefix in prefixes:
            pattern = re.compile(rf"{re.escape(prefix)}[\s:：-]*([A-Za-z][\w-]*)")
            for item in pattern.findall(content):
                found.add(item)
        return sorted(found)

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
            },
            "required": ["content"],
        }

