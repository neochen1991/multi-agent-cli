"""Tool 插件目录扫描与元数据加载。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class ToolPluginProfile(BaseModel):
    """描述一个可扩展 Tool 插件。"""

    tool_id: str
    name: str = ""
    description: str = ""
    runtime: str = "python"
    entry: str = "run.py"
    timeout_seconds: int = 60
    allowed_agents: List[str] = Field(default_factory=list)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    tool_path: str = ""


class ToolPluginLoader:
    """扫描 `extensions/tools/*/tool.json` 并加载插件。"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def list_all(self) -> List[ToolPluginProfile]:
        if not self.root.exists() or not self.root.is_dir():
            return []
        plugins: List[ToolPluginProfile] = []
        for tool_dir in sorted(path for path in self.root.iterdir() if path.is_dir()):
            plugin = self._load_tool(tool_dir)
            if plugin is not None:
                plugins.append(plugin)
        return plugins

    def get(self, tool_id: str) -> Optional[ToolPluginProfile]:
        target = str(tool_id or "").strip()
        if not target:
            return None
        for plugin in self.list_all():
            if plugin.tool_id == target:
                return plugin
        return None

    def _load_tool(self, tool_dir: Path) -> Optional[ToolPluginProfile]:
        tool_json = tool_dir / "tool.json"
        if not tool_json.exists():
            return None
        try:
            metadata = json.loads(tool_json.read_text(encoding="utf-8"))
        except Exception:
            return None
        try:
            return ToolPluginProfile.model_validate({**metadata, "tool_path": str(tool_dir)})
        except Exception:
            return None
