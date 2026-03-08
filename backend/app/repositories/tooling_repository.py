"""工具配置仓储。

负责持久化 Agent 的工具开关、连接器配置以及 Skill/Tool 相关策略。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.tooling import AgentToolingConfig


class ToolingRepository(ABC):
    """工具配置仓储抽象接口。"""

    @abstractmethod
    async def get(self) -> AgentToolingConfig:
        """读取当前生效的工具配置。"""
        pass

    @abstractmethod
    async def save(self, config: AgentToolingConfig) -> AgentToolingConfig:
        """保存并返回最新工具配置。"""
        pass


class InMemoryToolingRepository(ToolingRepository):
    """内存版工具配置仓储，适合测试和临时运行。"""

    def __init__(self):
        """初始化默认工具配置。"""
        self._config = AgentToolingConfig()

    async def get(self) -> AgentToolingConfig:
        """负责获取，并返回后续流程可直接消费的数据结果。"""
        return self._config

    async def save(self, config: AgentToolingConfig) -> AgentToolingConfig:
        """执行保存，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._config = config
        return config


class FileToolingRepository(ToolingRepository):
    """文件版工具配置仓储。"""

    def __init__(self, base_dir: Optional[str] = None):
        """初始化仓储并从 `tooling_config.json` 恢复配置。"""
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "tooling_config.json"
        self._lock = asyncio.Lock()
        self._config = AgentToolingConfig()
        self._load_from_disk()

    async def get(self) -> AgentToolingConfig:
        """负责获取，并返回后续流程可直接消费的数据结果。"""
        async with self._lock:
            return self._config

    async def save(self, config: AgentToolingConfig) -> AgentToolingConfig:
        """执行保存，并同步更新运行时状态、持久化结果或审计轨迹。"""
        async with self._lock:
            self._config = config
            self._persist_to_disk()
            return self._config

    def _load_from_disk(self) -> None:
        """读取本地配置文件；格式异常时回退为默认值。"""
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            self._config = AgentToolingConfig.model_validate(payload)
        except Exception:
            self._config = AgentToolingConfig()

    def _persist_to_disk(self) -> None:
        """将当前配置写入磁盘，并通过临时文件替换保证落盘完整性。"""
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._config.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._file)
