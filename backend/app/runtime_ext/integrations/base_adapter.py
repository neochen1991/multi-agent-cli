"""Base adapter protocol for external sync integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol


@dataclass
class AdapterBuildResult:
    """封装AdapterBuildResult相关数据结构或服务能力。"""
    provider: str
    action: str
    payload: Dict[str, Any]
    dry_run: bool = True


class ExternalSyncAdapter(Protocol):
    """封装ExternalSyncAdapter相关数据结构或服务能力。"""
    provider: str

    def build(self, *, action: str, payload: Dict[str, Any]) -> AdapterBuildResult:
        """构建构建，供后续节点或调用方直接使用。"""
        ...


__all__ = ["AdapterBuildResult", "ExternalSyncAdapter"]

