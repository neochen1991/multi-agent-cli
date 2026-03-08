"""
案例库工具模块（本地 Markdown 存储）

本模块提供案例库的本地存储和检索功能。

主要功能：
1. search: 根据关键词搜索案例
2. list: 列出所有案例
3. save: 保存新案例

存储格式：
每个案例存储为一个 Markdown 文件，包含：
- YAML front matter：案例元数据（JSON 格式）
- Markdown 正文：案例标题和描述

使用场景：
该工具由 RunbookAgent 使用，用于：
- 检索相似的历史故障案例
- 保存新的故障案例供后续参考
- 为当前故障提供处置建议

Case Library Tool (Local Markdown)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.tools.base import BaseTool, ToolResult


class CaseLibraryTool(BaseTool):
    """
    案例库工具（本地 Markdown 存储）

    提供案例的存储、检索和列表功能。
    案例存储为 Markdown 文件，包含 JSON 格式的元数据。

    存储路径：
    - 默认路径：/tmp/case_library
    - 可通过环境变量 CASE_LIBRARY_PATH 自定义

    操作类型：
    - search: 根据关键词搜索案例
    - list: 列出所有案例
    - save: 保存新案例
    """

    def __init__(self):
        """初始化案例库工具，创建存储目录"""
        super().__init__(name="case_library", description="本地案例库检索与写入")
        # 案例存储目录，可通过环境变量配置
        self._base_dir = Path(os.getenv("CASE_LIBRARY_PATH", "/tmp/case_library"))
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, action: str = "search", query: str = "", case: Dict[str, Any] = None, **kwargs) -> ToolResult:
        """
        执行案例库操作

        Args:
            action: 操作类型（search/list/save）
            query: 搜索关键词（search 操作）
            case: 案例数据（save 操作）
            **kwargs: 其他参数

        Returns:
            ToolResult: 操作结果
        """
        try:
            if action == "search":
                # 搜索案例
                return self._create_success_result({"items": self._search(query)})
            if action == "list":
                # 列出所有案例
                return self._create_success_result({"items": self._list_cases()})
            if action == "save":
                # 保存新案例
                if not case:
                    return self._create_error_result("case is required for save")
                case_id = self._save(case)
                return self._create_success_result({"case_id": case_id})
            return self._create_error_result(f"Unsupported action: {action}")
        except Exception as e:
            return self._create_error_result(str(e))

    def _list_cases(self) -> List[Dict[str, Any]]:
        """
        列出所有案例

        遍历存储目录，加载所有 Markdown 格式的案例文件。

        Returns:
            List[Dict[str, Any]]: 案例列表，按创建时间倒序排列
        """
        items = []
        for file in self._base_dir.glob("*.md"):
            loaded = self._load_case(file)
            if loaded:
                items.append(loaded)
        return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)

    def _search(self, query: str) -> List[Dict[str, Any]]:
        """
        搜索案例

        根据关键词在案例中搜索匹配的内容。

        Args:
            query: 搜索关键词

        Returns:
            List[Dict[str, Any]]: 匹配的案例列表
        """
        q = query.lower().strip()
        if not q:
            return self._list_cases()
        # 在案例的 JSON 表示中搜索关键词
        return [c for c in self._list_cases() if q in json.dumps(c, ensure_ascii=False).lower()]

    def _save(self, case: Dict[str, Any]) -> str:
        """
        保存案例

        将案例保存为 Markdown 文件，包含 YAML front matter。

        文件格式：
        ---
        {JSON 元数据}
        ---

        # 案例标题

        案例描述内容

        Args:
            case: 案例数据

        Returns:
            str: 案例ID
        """
        # 生成案例 ID
        case_id = case.get("id") or f"case_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        payload = {**case, "id": case_id}
        path = self._base_dir / f"{case_id}.md"

        # 构建 Markdown 内容
        body = (
            "---\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "---\n\n"
            f"# {payload.get('title', case_id)}\n\n"
            f"{payload.get('description', '')}\n"
        )
        path.write_text(body, encoding="utf-8")
        return case_id

    def _load_case(self, file: Path) -> Dict[str, Any]:
        """
        加载案例

        从 Markdown 文件中解析案例元数据。
        解析 YAML front matter 中的 JSON 元数据。

        Args:
            file: 案例文件路径

        Returns:
            Dict[str, Any]: 案例元数据，解析失败返回空字典
        """
        content = file.read_text(encoding="utf-8")
        # 检查是否有 YAML front matter
        if not content.startswith("---\n"):
            return {}
        # 分割 front matter 和正文
        parts = content.split("\n---\n", 1)
        if len(parts) < 2:
            return {}
        # 解析 JSON 元数据
        meta_raw = parts[0].replace("---\n", "", 1).strip()
        try:
            return json.loads(meta_raw)
        except json.JSONDecodeError:
            return {}

