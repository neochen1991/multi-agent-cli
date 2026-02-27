"""
Tooling configuration service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.config import settings
from app.models.tooling import AgentToolingConfig
from app.repositories.tooling_repository import (
    FileToolingRepository,
    InMemoryToolingRepository,
    ToolingRepository,
)


class ToolingService:
    def __init__(self, repository: Optional[ToolingRepository] = None):
        self._repository = repository or (
            FileToolingRepository()
            if settings.LOCAL_STORE_BACKEND == "file"
            else InMemoryToolingRepository()
        )

    async def get_config(self) -> AgentToolingConfig:
        return await self._repository.get()

    async def update_config(self, config: AgentToolingConfig) -> AgentToolingConfig:
        next_config = config.model_copy(update={"updated_at": datetime.utcnow()})
        return await self._repository.save(next_config)


tooling_service = ToolingService()

