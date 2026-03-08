"""
工具基类模块

本模块定义了所有工具的基类和通用接口：

核心组件：
- ToolResult: 工具执行结果模型
- BaseTool: 工具抽象基类

工具开发规范：
1. 所有工具必须继承 BaseTool
2. 必须实现 execute 方法
3. 可选实现 _get_parameters_schema 方法

使用示例：
    class MyTool(BaseTool):
        def __init__(self):
            super().__init__("my_tool", "我的工具描述")

        async def execute(self, **kwargs) -> ToolResult:
            # 实现具体逻辑
            return self._create_success_result({"result": "ok"})

Base Tool Class

所有工具的基类，定义统一的接口。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class ToolResult(BaseModel):
    """
    工具执行结果模型

    统一的工具执行结果格式，包含：
    - success: 是否执行成功
    - data: 结果数据字典
    - error: 错误信息（仅当失败时）
    - metadata: 元数据（如执行时间、来源等）
    """

    success: bool = Field(default=True, description="是否成功")
    data: Dict[str, Any] = Field(default_factory=dict, description="结果数据")
    error: Optional[str] = Field(None, description="错误信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class BaseTool(ABC):
    """
    工具抽象基类

    所有工具都需要继承此类并实现 execute 方法。

    设计模式：模板方法模式
    - execute: 抽象方法，子类必须实现
    - get_schema: 提供工具的 JSON Schema
    - _create_success_result: 创建成功结果的辅助方法
    - _create_error_result: 创建错误结果的辅助方法

    属性：
    - name: 工具名称，用于调用时识别
    - description: 工具描述，用于 Agent 理解工具用途
    """

    def __init__(self, name: str, description: str):
        """
        初始化工具

        Args:
            name: 工具名称（唯一标识符）
            description: 工具描述（供 Agent 理解用途）
        """
        self.name = name
        self.description = description

        logger.debug(
            "tool_initialized",
            name=name,
            description=description
        )

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        执行工具

        子类必须实现此方法，定义工具的具体执行逻辑。

        Args:
            **kwargs: 工具参数，根据具体工具而定

        Returns:
            ToolResult: 工具执行结果
        """
        pass

    def get_schema(self) -> Dict[str, Any]:
        """
        获取工具的 JSON Schema

        用于生成 OpenAI Function Calling 格式的工具定义。

        Returns:
            Dict[str, Any]: 包含 name、description、parameters 的 Schema
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._get_parameters_schema()
        }

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数的 JSON Schema

        子类可以覆盖此方法提供详细的参数 Schema。
        默认返回空对象，表示无参数要求。

        Returns:
            Dict[str, Any]: 参数的 JSON Schema
        """
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def _create_success_result(
        self,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        创建成功结果

        辅助方法，用于快速创建成功的执行结果。

        Args:
            data: 结果数据字典
            metadata: 可选的元数据

        Returns:
            ToolResult: 成功的执行结果
        """
        return ToolResult(
            success=True,
            data=data,
            metadata=metadata or {}
        )

    def _create_error_result(
        self,
        error: str,
        data: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        创建错误结果

        辅助方法，用于快速创建失败的执行结果。

        Args:
            error: 错误信息
            data: 可选的部分结果数据

        Returns:
            ToolResult: 失败的执行结果
        """
        return ToolResult(
            success=False,
            data=data or {},
            error=error
        )

    def __repr__(self) -> str:
        """返回工具的字符串表示"""
        return f"{self.__class__.__name__}(name={self.name})"

    def __str__(self) -> str:
        """返回工具名称"""
        return self.name
