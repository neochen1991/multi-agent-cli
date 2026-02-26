"""
LangChain Tool Adapter Layer
LangChain 工具适配层

将现有 BaseTool 适配为 LangChain Tool 格式，供 Agent 使用。
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import structlog
from langchain_core.tools import BaseTool as LCBaseTool, StructuredTool, tool
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.tools.log_parser import LogParserTool
from app.tools.git_tool import GitTool
from app.tools.ddd_analyzer import DDDAnalyzerTool
from app.tools.db_tool import DBTool
from app.tools.case_library import CaseLibraryTool

logger = structlog.get_logger()


# ============================================================================
# Pydantic Models for Tool Inputs
# ============================================================================


class ReadFileInput(BaseModel):
    """read_file 工具的输入参数"""

    file_path: str = Field(description="要读取的文件绝对路径")


class SearchInFilesInput(BaseModel):
    """search_in_files 工具的输入参数"""

    directory: str = Field(description="要搜索的目录路径")
    pattern: str = Field(description="搜索的正则表达式模式")
    file_pattern: str = Field(default="*.py", description="文件匹配模式，如 *.py, *.log")


class ListFilesInput(BaseModel):
    """list_files 工具的输入参数"""

    directory: str = Field(description="要列出的目录路径")
    recursive: bool = Field(default=True, description="是否递归列出子目录")


class ParseLogInput(BaseModel):
    """parse_log 工具的输入参数"""

    log_content: str = Field(description="要解析的日志内容")


class GitToolInput(BaseModel):
    """git_tool 工具的输入参数"""

    repo_path: str = Field(description="Git 仓库路径")
    action: str = Field(default="status", description="操作类型: status, log, blame")
    file_path: Optional[str] = Field(default=None, description="blame 操作需要的文件路径")
    limit: int = Field(default=20, description="log 操作的提交数量限制")


class DDDAnalyzerInput(BaseModel):
    """ddd_analyzer 工具的输入参数"""

    content: str = Field(description="要分析的内容")


class DBToolInput(BaseModel):
    """db_tool 工具的输入参数"""

    db_path: str = Field(description="数据库文件路径")
    action: str = Field(default="tables", description="操作类型: tables, query")
    query: str = Field(default="", description="SQL 查询语句（仅支持 SELECT）")
    limit: int = Field(default=100, description="查询结果行数限制")


class CaseLibraryInput(BaseModel):
    """case_library 工具的输入参数"""

    action: str = Field(default="search", description="操作类型: search, list, save")
    query: str = Field(default="", description="搜索关键词")
    case: Optional[Dict[str, Any]] = Field(default=None, description="要保存的案例数据")


# ============================================================================
# New File System Tools
# ============================================================================


@tool
def read_file(file_path: str) -> str:
    """
    读取本地文件内容，用于分析日志文件、配置文件等。

    Args:
        file_path: 文件的绝对路径

    Returns:
        文件内容字符串
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"错误：文件不存在: {file_path}"
        if not path.is_file():
            return f"错误：路径不是文件: {file_path}"

        # 限制文件大小，避免读取超大文件
        max_size = 10 * 1024 * 1024  # 10MB
        if path.stat().st_size > max_size:
            return f"错误：文件过大（超过 10MB），请使用 search_in_files 搜索特定内容"

        content = path.read_text(encoding="utf-8", errors="replace")
        logger.debug("file_read", file_path=file_path, size=len(content))
        return content
    except PermissionError:
        return f"错误：没有权限读取文件: {file_path}"
    except Exception as e:
        logger.error("read_file_failed", file_path=file_path, error=str(e))
        return f"错误：读取文件失败: {str(e)}"


@tool
def search_in_files(directory: str, pattern: str, file_pattern: str = "*.py") -> str:
    """
    在目录中搜索文件内容，支持正则表达式。

    Args:
        directory: 要搜索的目录路径
        pattern: 正则表达式搜索模式
        file_pattern: 文件匹配模式，默认 *.py

    Returns:
        匹配结果的格式化字符串
    """
    try:
        dir_path = Path(directory)
        if not dir_path.exists():
            return f"错误：目录不存在: {directory}"
        if not dir_path.is_dir():
            return f"错误：路径不是目录: {directory}"

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"错误：无效的正则表达式: {e}"

        results = []
        max_results = 100
        max_file_size = 5 * 1024 * 1024  # 5MB per file

        for file_path in dir_path.rglob(file_pattern):
            if not file_path.is_file():
                continue
            if file_path.stat().st_size > max_file_size:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        results.append(f"{file_path}:{i}: {line.strip()}")
                        if len(results) >= max_results:
                            break
            except Exception:
                continue

            if len(results) >= max_results:
                break

        if not results:
            return f"未找到匹配 '{pattern}' 的内容"

        return f"找到 {len(results)} 个匹配:\n" + "\n".join(results[:50])

    except Exception as e:
        logger.error("search_in_files_failed", directory=directory, error=str(e))
        return f"错误：搜索失败: {str(e)}"


@tool
def list_files(directory: str, recursive: bool = True) -> str:
    """
    列出目录下的文件和子目录。

    Args:
        directory: 要列出的目录路径
        recursive: 是否递归列出子目录，默认 True

    Returns:
        文件列表的格式化字符串
    """
    try:
        dir_path = Path(directory)
        if not dir_path.exists():
            return f"错误：目录不存在: {directory}"
        if not dir_path.is_dir():
            return f"错误：路径不是目录: {directory}"

        items = []
        max_items = 500

        if recursive:
            for item in dir_path.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(dir_path)
                    size = item.stat().st_size
                    items.append(f"[文件] {rel_path} ({size} bytes)")
                elif item.is_dir():
                    rel_path = item.relative_to(dir_path)
                    items.append(f"[目录] {rel_path}/")
                if len(items) >= max_items:
                    items.append(f"... (已达到最大显示数量 {max_items})")
                    break
        else:
            for item in dir_path.iterdir():
                if item.is_file():
                    size = item.stat().st_size
                    items.append(f"[文件] {item.name} ({size} bytes)")
                elif item.is_dir():
                    items.append(f"[目录] {item.name}/")
                if len(items) >= max_items:
                    items.append(f"... (已达到最大显示数量 {max_items})")
                    break

        if not items:
            return f"目录 {directory} 为空"

        return f"目录 {directory} 内容:\n" + "\n".join(items)

    except PermissionError:
        return f"错误：没有权限访问目录: {directory}"
    except Exception as e:
        logger.error("list_files_failed", directory=directory, error=str(e))
        return f"错误：列出目录失败: {str(e)}"


# ============================================================================
# BaseTool to LangChain Tool Adapter
# ============================================================================


class BaseToolAdapter(StructuredTool):
    """
    将自定义 BaseTool 适配为 LangChain StructuredTool。

    这个适配器允许现有的 BaseTool 实例在 LangChain Agent 中使用。
    """

    base_tool: BaseTool
    args_schema: Type[BaseModel]

    def __init__(self, base_tool: BaseTool, args_schema: Type[BaseModel]):
        """
        初始化适配器。

        Args:
            base_tool: 自定义 BaseTool 实例
            args_schema: Pydantic 模型定义参数 schema
        """
        super().__init__(
            name=base_tool.name,
            description=base_tool.description,
            args_schema=args_schema,
        )
        self.base_tool = base_tool

    def _run(self, **kwargs) -> str:
        """同步执行（包装异步执行）"""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 如果已经在事件循环中，创建任务
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.base_tool.execute(**kwargs))
                result = future.result()
        else:
            # 否则直接运行
            result = asyncio.run(self.base_tool.execute(**kwargs))

        return self._format_result(result)

    async def _arun(self, **kwargs) -> str:
        """异步执行"""
        result = await self.base_tool.execute(**kwargs)
        return self._format_result(result)

    def _format_result(self, result: ToolResult) -> str:
        """格式化工具执行结果为字符串"""
        if result.success:
            import json

            return json.dumps(result.data, ensure_ascii=False, indent=2)
        else:
            return f"错误：{result.error}"


# ============================================================================
# Tool Factory Functions
# ============================================================================


def create_parse_log_tool() -> StructuredTool:
    """创建日志解析工具的 LangChain 适配器"""
    return BaseToolAdapter(
        base_tool=LogParserTool(),
        args_schema=ParseLogInput,
    )


def create_git_tool() -> StructuredTool:
    """创建 Git 工具的 LangChain 适配器"""
    return BaseToolAdapter(
        base_tool=GitTool(),
        args_schema=GitToolInput,
    )


def create_ddd_analyzer_tool() -> StructuredTool:
    """创建 DDD 分析工具的 LangChain 适配器"""
    return BaseToolAdapter(
        base_tool=DDDAnalyzerTool(),
        args_schema=DDDAnalyzerInput,
    )


def create_db_tool() -> StructuredTool:
    """创建数据库工具的 LangChain 适配器"""
    return BaseToolAdapter(
        base_tool=DBTool(),
        args_schema=DBToolInput,
    )


def create_case_library_tool() -> StructuredTool:
    """创建案例库工具的 LangChain 适配器"""
    return BaseToolAdapter(
        base_tool=CaseLibraryTool(),
        args_schema=CaseLibraryInput,
    )


# ============================================================================
# Tool Registry
# ============================================================================

# 工具注册表：名称 -> 创建函数
TOOL_REGISTRY: Dict[str, Callable[[], LCBaseTool]] = {
    "read_file": lambda: read_file,
    "search_in_files": lambda: search_in_files,
    "list_files": lambda: list_files,
    "parse_log": create_parse_log_tool,
    "git_tool": create_git_tool,
    "ddd_analyzer": create_ddd_analyzer_tool,
    "db_tool": create_db_tool,
    "case_library": create_case_library_tool,
}


def get_tool(name: str) -> Optional[LCBaseTool]:
    """
    根据名称获取 LangChain 工具实例。

    Args:
        name: 工具名称

    Returns:
        LangChain 工具实例，如果不存在返回 None
    """
    factory = TOOL_REGISTRY.get(name)
    if factory:
        return factory()
    return None


def get_tools(names: List[str]) -> List[LCBaseTool]:
    """
    根据名称列表获取多个 LangChain 工具实例。

    Args:
        names: 工具名称列表

    Returns:
        LangChain 工具实例列表
    """
    tools = []
    for name in names:
        tool = get_tool(name)
        if tool:
            tools.append(tool)
        else:
            logger.warning("tool_not_found", name=name)
    return tools


def get_all_tools() -> List[LCBaseTool]:
    """
    获取所有可用的 LangChain 工具实例。

    Returns:
        所有 LangChain 工具实例列表
    """
    return [factory() for factory in TOOL_REGISTRY.values()]


# ============================================================================
# Convenience Exports
# ============================================================================

__all__ = [
    # New file system tools
    "read_file",
    "search_in_files",
    "list_files",
    # Tool adapters
    "BaseToolAdapter",
    "create_parse_log_tool",
    "create_git_tool",
    "create_ddd_analyzer_tool",
    "create_db_tool",
    "create_case_library_tool",
    # Tool registry
    "TOOL_REGISTRY",
    "get_tool",
    "get_tools",
    "get_all_tools",
    # Input schemas
    "ReadFileInput",
    "SearchInFilesInput",
    "ListFilesInput",
    "ParseLogInput",
    "GitToolInput",
    "DDDAnalyzerInput",
    "DBToolInput",
    "CaseLibraryInput",
]