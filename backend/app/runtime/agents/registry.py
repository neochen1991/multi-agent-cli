"""
Tool Registry
工具注册表

管理可用的 LangChain 工具，提供工具注册和获取功能。
简化自 AgentFactory，专注于工具管理。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Type, Union

import structlog
from langchain_core.tools import BaseTool as LCBaseTool

logger = structlog.get_logger()


class ToolRegistry:
    """
    工具注册表

    管理可用工具的中心化注册表，支持：
    - 注册工具实例
    - 按名称获取工具
    - 批量获取工具

    使用方式：
        registry = ToolRegistry()
        registry.register(my_tool)
        tool = registry.get("my_tool")
        tools = registry.get_all(["tool1", "tool2"])
    """

    _tools: Dict[str, LCBaseTool] = {}

    @classmethod
    def register(cls, tool: LCBaseTool) -> None:
        """
        注册一个工具。

        Args:
            tool: LangChain 工具实例
        """
        if not isinstance(tool, LCBaseTool):
            raise TypeError(f"Expected BaseTool, got {type(tool)}")
        cls._tools[tool.name] = tool
        logger.debug("tool_registered", name=tool.name)

    @classmethod
    def register_many(cls, tools: List[LCBaseTool]) -> None:
        """
        批量注册工具。

        Args:
            tools: 工具列表
        """
        for tool in tools:
            cls.register(tool)

    @classmethod
    def get(cls, name: str) -> Optional[LCBaseTool]:
        """
        获取指定名称的工具。

        Args:
            name: 工具名称

        Returns:
            工具实例，如果不存在返回 None
        """
        return cls._tools.get(name)

    @classmethod
    def get_all(cls, names: List[str]) -> List[LCBaseTool]:
        """
        批量获取工具。

        Args:
            names: 工具名称列表

        Returns:
            找到的工具列表（跳过不存在的工具）
        """
        tools = []
        for name in names:
            tool = cls._tools.get(name)
            if tool:
                tools.append(tool)
            else:
                logger.warning("tool_not_found", name=name)
        return tools

    @classmethod
    def list_tools(cls) -> List[str]:
        """
        列出所有已注册的工具名称。

        Returns:
            工具名称列表
        """
        return list(cls._tools.keys())

    @classmethod
    def has(cls, name: str) -> bool:
        """
        检查工具是否已注册。

        Args:
            name: 工具名称

        Returns:
            是否存在
        """
        return name in cls._tools

    @classmethod
    def clear(cls) -> None:
        """清除所有已注册的工具"""
        cls._tools.clear()
        logger.debug("tool_registry_cleared")

    @classmethod
    def initialize_from_tools_module(cls) -> None:
        """
        从 app.tools.langchain_tools 模块初始化工具。

        加载所有预定义的工具到注册表。
        """
        try:
            from app.tools.langchain_tools import get_tools, get_tool_names
            names = get_tool_names()
            tools = get_tools(names)
            cls.register_many(tools)
            logger.info("tool_registry_initialized", count=len(tools))
        except Exception as e:
            logger.error("tool_registry_init_failed", error=str(e))


# ============================================================================
# Module-level convenience functions
# ============================================================================


def get_tool(name: str) -> Optional[LCBaseTool]:
    """获取指定名称的工具"""
    return ToolRegistry.get(name)


def get_tools(names: List[str]) -> List[LCBaseTool]:
    """批量获取工具"""
    return ToolRegistry.get_all(names)


def register_tool(tool: LCBaseTool) -> None:
    """注册工具"""
    ToolRegistry.register(tool)


__all__ = [
    "ToolRegistry",
    "get_tool",
    "get_tools",
    "register_tool",
]