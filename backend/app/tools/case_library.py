"""
案例库工具（本地 Markdown）
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
    def __init__(self):
        super().__init__(name="case_library", description="本地案例库检索与写入")
        self._base_dir = Path(os.getenv("CASE_LIBRARY_PATH", "/tmp/case_library"))
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, action: str = "search", query: str = "", case: Dict[str, Any] = None, **kwargs) -> ToolResult:
        try:
            if action == "search":
                return self._create_success_result({"items": self._search(query)})
            if action == "list":
                return self._create_success_result({"items": self._list_cases()})
            if action == "save":
                if not case:
                    return self._create_error_result("case is required for save")
                case_id = self._save(case)
                return self._create_success_result({"case_id": case_id})
            return self._create_error_result(f"Unsupported action: {action}")
        except Exception as e:
            return self._create_error_result(str(e))

    def _list_cases(self) -> List[Dict[str, Any]]:
        items = []
        for file in self._base_dir.glob("*.md"):
            loaded = self._load_case(file)
            if loaded:
                items.append(loaded)
        return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)

    def _search(self, query: str) -> List[Dict[str, Any]]:
        q = query.lower().strip()
        if not q:
            return self._list_cases()
        return [c for c in self._list_cases() if q in json.dumps(c, ensure_ascii=False).lower()]

    def _save(self, case: Dict[str, Any]) -> str:
        case_id = case.get("id") or f"case_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        payload = {**case, "id": case_id}
        path = self._base_dir / f"{case_id}.md"
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
        content = file.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            return {}
        parts = content.split("\n---\n", 1)
        if len(parts) < 2:
            return {}
        meta_raw = parts[0].replace("---\n", "", 1).strip()
        try:
            return json.loads(meta_raw)
        except json.JSONDecodeError:
            return {}

