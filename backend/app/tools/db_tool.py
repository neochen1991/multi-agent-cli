"""
数据库工具
Database Tool
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from app.tools.base import BaseTool, ToolResult


class DBTool(BaseTool):
    """封装DBTool相关数据结构或服务能力。"""
    def __init__(self):
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        super().__init__(name="db_tool", description="执行只读数据库查询（SQLite）")

    async def execute(
        self,
        db_path: str,
        action: str = "tables",
        query: str = "",
        limit: int = 100,
        **kwargs,
    ) -> ToolResult:
        """执行execute相关逻辑，并为当前模块提供可复用的处理能力。"""
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            if action == "tables":
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                return self._create_success_result({"tables": rows})

            if action == "query":
                if not query.strip():
                    conn.close()
                    return self._create_error_result("query is required")
                if not query.strip().lower().startswith("select"):
                    conn.close()
                    return self._create_error_result("only SELECT queries are allowed")
                cur.execute(f"{query.rstrip(';')} LIMIT {limit}")
                rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                return self._create_success_result({"rows": rows, "count": len(rows)})

            conn.close()
            return self._create_error_result(f"Unsupported action: {action}")
        except Exception as e:
            return self._create_error_result(str(e))

    def _get_parameters_schema(self) -> Dict[str, Any]:
        """负责获取parametersSchema，并返回后续流程可直接消费的数据结果。"""
        return {
            "type": "object",
            "properties": {
                "db_path": {"type": "string"},
                "action": {"type": "string", "enum": ["tables", "query"]},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["db_path"],
        }

