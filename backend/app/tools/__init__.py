"""
工具模块
Tools Module
"""

from app.tools.base import BaseTool, ToolResult
from app.tools.log_parser import LogParserTool
from app.tools.git_tool import GitTool
from app.tools.ddd_analyzer import DDDAnalyzerTool
from app.tools.db_tool import DBTool
from app.tools.case_library import CaseLibraryTool

# LangChain tool adapters and new file system tools
from app.tools.langchain_tools import (
    # New file system tools
    read_file,
    search_in_files,
    list_files,
    # Tool adapters
    BaseToolAdapter,
    create_parse_log_tool,
    create_git_tool,
    create_ddd_analyzer_tool,
    create_db_tool,
    create_case_library_tool,
    # Tool registry
    TOOL_REGISTRY,
    get_tool,
    get_tools,
    get_all_tools,
    # Input schemas
    ReadFileInput,
    SearchInFilesInput,
    ListFilesInput,
    ParseLogInput,
    GitToolInput,
    DDDAnalyzerInput,
    DBToolInput,
    CaseLibraryInput,
)

__all__ = [
    # Base tools
    "BaseTool",
    "ToolResult",
    "LogParserTool",
    "GitTool",
    "DDDAnalyzerTool",
    "DBTool",
    "CaseLibraryTool",
    # LangChain tools
    "read_file",
    "search_in_files",
    "list_files",
    "BaseToolAdapter",
    "create_parse_log_tool",
    "create_git_tool",
    "create_ddd_analyzer_tool",
    "create_db_tool",
    "create_case_library_tool",
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
