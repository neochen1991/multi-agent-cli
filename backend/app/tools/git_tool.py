"""
Git 工具
Git Tool
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, Optional

from app.tools.base import BaseTool, ToolResult


class GitTool(BaseTool):
    def __init__(self):
        super().__init__(name="git_tool", description="执行只读 Git 分析操作")

    async def execute(
        self,
        repo_path: str,
        action: str = "status",
        file_path: Optional[str] = None,
        limit: int = 20,
        **kwargs,
    ) -> ToolResult:
        try:
            if action == "status":
                cmd = ["git", "status", "--short"]
            elif action == "log":
                cmd = ["git", "log", f"-n{limit}", "--oneline"]
            elif action == "blame":
                if not file_path:
                    return self._create_error_result("file_path is required for blame")
                cmd = ["git", "blame", "-L", "1,200", file_path]
            else:
                return self._create_error_result(f"Unsupported action: {action}")

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

