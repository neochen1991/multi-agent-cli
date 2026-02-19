"""
工具基类
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
    """工具执行结果"""
    
    success: bool = Field(default=True, description="是否成功")
    data: Dict[str, Any] = Field(default_factory=dict, description="结果数据")
    error: Optional[str] = Field(None, description="错误信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class BaseTool(ABC):
    """
    工具基类
    
    所有工具都需要继承此类并实现 execute 方法。
    """
    
    def __init__(self, name: str, description: str):
        """
        初始化工具
        
        Args:
            name: 工具名称
            description: 工具描述
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
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            工具执行结果
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """
        获取工具的 JSON Schema
        
        Returns:
            工具的 JSON Schema
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
        
        Returns:
            参数的 JSON Schema
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
        
        Args:
            data: 结果数据
            metadata: 元数据
            
        Returns:
            成功的 ToolResult
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
        
        Args:
            error: 错误信息
            data: 可选的部分结果数据
            
        Returns:
            错误的 ToolResult
        """
        return ToolResult(
            success=False,
            data=data or {},
            error=error
        )
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
    
    def __str__(self) -> str:
        return self.name
