"""Connector protocol definitions."""

from __future__ import annotations

from typing import Any, Dict, Protocol


class ConnectorProtocol(Protocol):
    name: str
    resource_type: str

    async def fetch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch resource snapshot for an agent/tool call."""
        ...

