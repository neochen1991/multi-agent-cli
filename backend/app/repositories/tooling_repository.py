"""
Tooling configuration repository.
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
    @abstractmethod
    async def get(self) -> AgentToolingConfig:
        pass

    @abstractmethod
    async def save(self, config: AgentToolingConfig) -> AgentToolingConfig:
        pass


class InMemoryToolingRepository(ToolingRepository):
    def __init__(self):
        self._config = AgentToolingConfig()

    async def get(self) -> AgentToolingConfig:
        return self._config

    async def save(self, config: AgentToolingConfig) -> AgentToolingConfig:
        self._config = config
        return config


class FileToolingRepository(ToolingRepository):
    def __init__(self, base_dir: Optional[str] = None):
        root = Path(base_dir or settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "tooling_config.json"
        self._lock = asyncio.Lock()
        self._config = AgentToolingConfig()
        self._load_from_disk()

    async def get(self) -> AgentToolingConfig:
        async with self._lock:
            return self._config

    async def save(self, config: AgentToolingConfig) -> AgentToolingConfig:
        async with self._lock:
            self._config = config
            self._persist_to_disk()
            return self._config

    def _load_from_disk(self) -> None:
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            self._config = AgentToolingConfig.model_validate(payload)
        except Exception:
            self._config = AgentToolingConfig()

    def _persist_to_disk(self) -> None:
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._config.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._file)

