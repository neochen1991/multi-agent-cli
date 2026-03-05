"""Base adapter protocol for external sync integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol


@dataclass
class AdapterBuildResult:
    provider: str
    action: str
    payload: Dict[str, Any]
    dry_run: bool = True


class ExternalSyncAdapter(Protocol):
    provider: str

    def build(self, *, action: str, payload: Dict[str, Any]) -> AdapterBuildResult:
        ...


__all__ = ["AdapterBuildResult", "ExternalSyncAdapter"]

