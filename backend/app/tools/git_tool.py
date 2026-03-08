"""
Git 工具模块

本模块提供 Git 仓库的只读分析功能，用于代码分析专家（CodeAgent）查询代码仓库信息。

功能说明：
- status: 查看仓库状态，了解当前分支、修改文件等
- log: 查看提交历史，了解最近的代码变更
- blame: 查看文件作者信息，了解代码责任归属

使用示例：
    tool = GitTool()
    result = await tool.execute(repo_path="/path/to/repo", action="log", limit=10)

安全说明：
- 仅执行只读操作，不会修改仓库内容
- 通过 subprocess 安全执行命令

Git Tool
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, Optional

from app.tools.base import BaseTool, ToolResult


class GitTool(BaseTool):
    """
    Git 只读分析工具

    提供 Git 仓库的只读查询功能，支持以下操作：
    - status: 查看仓库状态（修改、暂存、未跟踪文件）
    - log: 查看提交历史
    - blame: 查看文件作者信息

    该工具由 CodeAgent 使用，用于分析代码变更历史和责任归属。
    """

    def __init__(self):
        """初始化 Git 工具"""
        super().__init__(name="git_tool", description="执行只读 Git 分析操作")

    async def execute(
        self,
        repo_path: str,
        action: str = "status",
        file_path: Optional[str] = None,
        limit: int = 20,
        **kwargs,
    ) -> ToolResult:
        """
        执行 Git 操作

        Args:
            repo_path: Git 仓库路径
            action: 操作类型（status/log/blame）
            file_path: 文件路径（blame 操作必需）
            limit: 返回记录数量限制（log 操作）
            **kwargs: 其他参数

        Returns:
            ToolResult: 包含 Git 命令输出的结果
        """
        try:
            # 根据操作类型构建命令
            if action == "status":
                # 查看仓库状态
                cmd = ["git", "status", "--short"]
            elif action == "log":
                # 查看最近 N 条提交记录
                cmd = ["git", "log", f"-n{limit}", "--oneline"]
            elif action == "blame":
                # 查看文件作者信息
                if not file_path:
                    return self._create_error_result("file_path is required for blame")
                cmd = ["git", "blame", "-L", "1,200", file_path]
            else:
                return self._create_error_result(f"Unsupported action: {action}")

            # 执行 Git 命令
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return self._create_error_result(result.stderr.strip() or "git command failed")
            return self._create_success_result(
                {
                    "action": action,
                    "output": result.stdout,
                }
            )
        except Exception as e:
            return self._create_error_result(str(e))

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数 JSON Schema

        定义工具参数的结构，用于 OpenAI Function Calling。

        Returns:
            Dict[str, Any]: 参数 Schema
        """
        return {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string"},
                "action": {"type": "string", "enum": ["status", "log", "blame"]},
                "file_path": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["repo_path"],
        }

