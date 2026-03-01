"""LangGraph runtime package exports.

Keep imports lazy to avoid circular dependency during test collection.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "LangGraphRuntimeOrchestrator",
    "langgraph_runtime_orchestrator",
    "RuntimeSessionStore",
    "runtime_session_store",
    "RuntimeTaskRegistry",
    "runtime_task_registry",
]


def __getattr__(name: str) -> Any:
    if name in {"LangGraphRuntimeOrchestrator", "langgraph_runtime_orchestrator"}:
        mod = import_module("app.runtime.langgraph_runtime")
        return getattr(mod, name)
    if name in {"RuntimeSessionStore", "runtime_session_store"}:
        mod = import_module("app.runtime.session_store")
        return getattr(mod, name)
    if name in {"RuntimeTaskRegistry", "runtime_task_registry"}:
        mod = import_module("app.runtime.task_registry")
        return getattr(mod, name)
    raise AttributeError(f"module 'app.runtime' has no attribute {name!r}")
