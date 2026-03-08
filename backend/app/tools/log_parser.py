"""
日志解析工具模块

本模块提供日志解析功能，用于从应用日志中提取关键信息。

主要功能：
1. 解析异常栈：识别 Java 异常类型、消息、堆栈跟踪
2. 解析日志行：提取时间戳、日志级别、Logger 名称
3. 提取 URL：识别 HTTP 请求路径
4. 提取类名：识别 Java 类名
5. 提取 SQL：识别 SQL 语句
6. 提取 Trace ID：识别分布式追踪 ID

数据结构：
- ParsedException: 解析后的异常信息
- ParsedLogLine: 解析后的日志行

Log Parser Tool

解析各种格式的应用日志，提取关键信息。
"""

import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import structlog

from app.tools.base import BaseTool, ToolResult

logger = structlog.get_logger()


@dataclass
class ParsedException:
    """
    解析后的异常信息

    包含完整的异常堆栈信息：
    - exception_type: 异常类型（如 NullPointerException）
    - message: 异常消息
    - stack_trace: 堆栈跟踪列表
    - cause: 根本原因（可选）
    """
    exception_type: str
    message: str
    stack_trace: List[Dict[str, Any]]
    cause: Optional[str] = None


@dataclass
class ParsedLogLine:
    """
    解析后的日志行

    包含标准化的日志行信息：
    - timestamp: 时间戳
    - level: 日志级别（DEBUG/INFO/WARN/ERROR）
    - logger: Logger 名称
    - message: 日志消息
    - thread: 线程名（可选）
    - trace_id: 分布式追踪 ID（可选）
    """
    timestamp: str
    level: str
    logger: str
    message: str
    thread: Optional[str] = None
    trace_id: Optional[str] = None


class LogParserTool(BaseTool):
    """
    日志解析工具

    提供以下功能：
    1. 解析异常栈：识别 Java 异常的完整堆栈
    2. 解析日志行：提取时间戳、级别、消息等
    3. 提取 URL：识别 HTTP 请求路径
    4. 提取类名：识别 Java 类名
    5. 提取 SQL：识别 SQL 语句
    6. 提取 Trace ID：识别分布式追踪 ID

    该工具由 LogAgent 使用，是故障分析的核心工具之一。
    """

    # Java 异常栈正则表达式
    # 匹配格式：ExceptionType: message
    EXCEPTION_PATTERN = re.compile(
        r'^([\w.]+(?:Exception|Error|Throwable)):\s*(.*)$'
    )
    # 匹配堆栈行：at package.Class.method(File.java:123)
    STACK_TRACE_PATTERN = re.compile(
        r'^\s+at\s+([\w.]+)\.([\w<>$]+)\(([\w.]+):(\d+)\)$'
    )
    # 匹配 Caused by 行
    CAUSED_BY_PATTERN = re.compile(
        r'^Caused by:\s*([\w.]+(?:Exception|Error|Throwable)):\s*(.*)$'
    )

    # 日志格式正则（支持多种格式）
    LOG_PATTERNS = [
        # Log4j 格式: 2024-01-15 10:30:45,123 ERROR [logger] [thread] message
        re.compile(
            r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,.]\d+)\s+'
            r'(TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s+'
            r'\[?([\w.-]+)\]?\s*'
            r'(?:\[([^\]]+)\])?\s*'
            r'(.*)$'
        ),
        # 简单格式: [ERROR] 2024-01-15 10:30:45 - message
        re.compile(
            r'^\[(TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\]\s*'
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*-\s*'
            r'(.*)$'
        ),
    ]

    # URL 正则：匹配 HTTP URL 和相对路径
    URL_PATTERN = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+|'
        r'/[a-zA-Z][a-zA-Z0-9_/-]*(?:\?[^\s]*)?'
    )

    # 类名正则：匹配驼峰命名的类名
    CLASS_NAME_PATTERN = re.compile(
        r'\b([A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)*)\b'
    )

    # SQL 正则：匹配 SQL 关键字
    SQL_PATTERN = re.compile(
        r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE)\b',
        re.IGNORECASE
    )

    # Trace ID 正则：匹配常见的追踪 ID 格式
    TRACE_ID_PATTERN = re.compile(
        r'(?:trace[_-]?id|traceid|request[_-]?id)[=:\s]*([a-f0-9-]{16,}|[\w-]{8,})',
        re.IGNORECASE
    )
    
    def __init__(self):
        """初始化日志解析工具"""
        super().__init__(
            name="log_parser",
            description="解析应用日志，提取异常信息、URL、类名等关键信息"
        )

    async def execute(self, log_content: str, **kwargs) -> ToolResult:
        """
        执行日志解析

        解析日志内容，提取以下信息：
        - exceptions: 解析后的异常列表
        - log_lines: 解析后的日志行列表
        - urls: 提取的 URL 列表
        - class_names: 提取的类名列表
        - sqls: 提取的 SQL 语句列表
        - trace_ids: 提取的追踪 ID 列表

        Args:
            log_content: 日志内容
            **kwargs: 其他参数

        Returns:
            ToolResult: 包含解析结果的数据
        """
        try:
            result = {
                "exceptions": self.parse_exceptions(log_content),
                "log_lines": self.parse_log_lines(log_content),
                "urls": self.extract_urls(log_content),
                "class_names": self.extract_class_names(log_content),
                "sqls": self.extract_sqls(log_content),
                "trace_ids": self.extract_trace_ids(log_content),
            }

            return self._create_success_result(result)

        except Exception as e:
            logger.error("log_parse_failed", error=str(e))
            return self._create_error_result(str(e))

    def parse_exceptions(self, log_content: str) -> List[Dict[str, Any]]:
        """
        解析异常信息

        从日志中提取 Java 异常堆栈，包括：
        - 异常类型（如 NullPointerException）
        - 异常消息
        - 堆栈跟踪（类名、方法名、文件名、行号）
        - Caused by 信息

        Args:
            log_content: 日志内容

        Returns:
            List[Dict[str, Any]]: 异常信息列表
        """
        lines = log_content.strip().split('\n')
        exceptions = []
        current_exception = None
        stack_trace = []

        for line in lines:
            # 检查是否是异常开头
            match = self.EXCEPTION_PATTERN.match(line)
            if match:
                # 保存上一个异常
                if current_exception:
                    current_exception['stack_trace'] = stack_trace
                    exceptions.append(current_exception)

                # 创建新异常
                current_exception = {
                    'type': match.group(1),
                    'message': match.group(2),
                    'stack_trace': [],
                    'cause': None
                }
                stack_trace = []

            # 检查是否是 Caused by
            elif current_exception:
                caused_match = self.CAUSED_BY_PATTERN.match(line)
                if caused_match:
                    current_exception['cause'] = {
                        'type': caused_match.group(1),
                        'message': caused_match.group(2)
                    }

                # 检查是否是堆栈行
                stack_match = self.STACK_TRACE_PATTERN.match(line)
                if stack_match:
                    stack_trace.append({
                        'class': stack_match.group(1),
                        'method': stack_match.group(2),
                        'file': stack_match.group(3),
                        'line': int(stack_match.group(4))
                    })

        # 添加最后一个异常
        if current_exception:
            current_exception['stack_trace'] = stack_trace
            exceptions.append(current_exception)

        return exceptions

    def parse_log_lines(self, log_content: str) -> List[Dict[str, Any]]:
        """
        解析日志行

        从日志中提取结构化的日志行信息，支持多种日志格式：
        - Log4j 格式
        - 简单格式

        Args:
            log_content: 日志内容

        Returns:
            List[Dict[str, Any]]: 解析后的日志行列表
        """
        lines = log_content.strip().split('\n')
        parsed_lines = []

        for line in lines:
            for pattern in self.LOG_PATTERNS:
                match = pattern.match(line)
                if match:
                    groups = match.groups()

                    # 根据匹配的格式解析
                    if len(groups) == 5:
                        # Log4j 格式
                        parsed_lines.append({
                            'timestamp': groups[0],
                            'level': groups[1],
                            'logger': groups[2],
                            'thread': groups[3],
                            'message': groups[4]
                        })
                    elif len(groups) == 3:
                        # 简单格式
                        parsed_lines.append({
                            'level': groups[0],
                            'timestamp': groups[1],
                            'message': groups[2],
                            'logger': None,
                            'thread': None
                        })
                    break

        return parsed_lines

    def extract_urls(self, content: str) -> List[str]:
        """
        提取 URL

        从内容中提取 HTTP URL 和相对路径。

        Args:
            content: 内容

        Returns:
            List[str]: URL 列表（去重）
        """
        return list(set(self.URL_PATTERN.findall(content)))

    def extract_class_names(self, content: str) -> List[str]:
        """
        提取类名

        从内容中提取 Java 类名（驼峰命名）。

        Args:
            content: 内容

        Returns:
            List[str]: 类名列表（去重、过滤）
        """
        # 过滤常见的非类名
        excludes = {
            'ERROR', 'WARN', 'INFO', 'DEBUG', 'TRACE', 'FATAL',
            'NULL', 'TRUE', 'FALSE', 'GET', 'POST', 'PUT', 'DELETE',
            'ID', 'UUID', 'URL', 'URI', 'JSON', 'XML', 'HTTP', 'HTTPS',
            'JVM', 'GC', 'CPU', 'IO', 'SQL', 'JPQL',
        }

        matches = self.CLASS_NAME_PATTERN.findall(content)
        return list(set(m for m in matches if m not in excludes and len(m) > 2))

    def extract_sqls(self, content: str) -> List[str]:
        """
        提取 SQL 语句

        从内容中提取包含 SQL 关键字的行。

        Args:
            content: 内容

        Returns:
            List[str]: SQL 语句列表
        """
        lines = content.split('\n')
        sqls = []

        for line in lines:
            if self.SQL_PATTERN.search(line):
                # 尝试提取完整的 SQL 语句
                sqls.append(line.strip())

        return sqls

    def extract_trace_ids(self, content: str) -> List[str]:
        """
        提取 Trace ID

        从内容中提取分布式追踪 ID。

        Args:
            content: 内容

        Returns:
            List[str]: Trace ID 列表（去重）
        """
        matches = self.TRACE_ID_PATTERN.findall(content)
        return list(set(matches))

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数 JSON Schema

        Returns:
            Dict[str, Any]: 参数 Schema
        """
        return {
            "type": "object",
            "properties": {
                "log_content": {
                    "type": "string",
                    "description": "要解析的日志内容"
                }
            },
            "required": ["log_content"]
        }
