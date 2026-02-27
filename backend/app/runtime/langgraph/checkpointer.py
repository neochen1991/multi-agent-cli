"""
Checkpointer Factory for LangGraph persistence.

Creates appropriate checkpointer based on configuration:
- MemorySaver for development/testing
- AsyncSqliteSaver for production with persistence
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from app.config import Settings

logger = structlog.get_logger()


def create_checkpointer(settings: "Settings") -> "BaseCheckpointSaver":
    """
    Create a checkpointer based on configuration.

    Args:
        settings: Application settings instance

    Returns:
        BaseCheckpointSaver instance (MemorySaver or AsyncSqliteSaver)

    Raises:
        ImportError: If sqlite backend is requested but dependencies are missing
    """
    backend = str(settings.CHECKPOINT_BACKEND or "memory").strip().lower()

    if backend == "sqlite":
        return _create_sqlite_checkpointer(settings)
    else:
        logger.info(
            "checkpointer_created",
            backend="memory",
            reason="sqlite not requested or not available",
        )
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()


def _create_sqlite_checkpointer(settings: "Settings") -> "BaseCheckpointSaver":
    """
    Create a SQLite-based checkpointer with proper directory setup.

    Args:
        settings: Application settings instance

    Returns:
        AsyncSqliteSaver instance
    """
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError as e:
        logger.warning(
            "sqlite_checkpointer_unavailable",
            error=str(e),
            fallback="memory",
        )
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

    db_path = Path(settings.CHECKPOINT_SQLITE_PATH)

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "sqlite_checkpointer_created",
        path=str(db_path),
        parent_exists=db_path.parent.exists(),
    )

    return AsyncSqliteSaver.from_conn_string(str(db_path))


async def close_checkpointer(checkpointer: "BaseCheckpointSaver") -> None:
    """
    Close checkpointer resources if applicable.

    Args:
        checkpointer: The checkpointer instance to close
    """
    # AsyncSqliteSaver has a close method
    if hasattr(checkpointer, "close"):
        try:
            await checkpointer.close()
            logger.info("checkpointer_closed", type=type(checkpointer).__name__)
        except Exception as e:
            logger.warning(
                "checkpointer_close_failed",
                error=str(e),
                type=type(checkpointer).__name__,
            )


__all__ = [
    "create_checkpointer",
    "close_checkpointer",
]