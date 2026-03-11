"""Build a lightweight lock-wait graph from database session snapshots."""

from __future__ import annotations

from typing import Any, Dict, List


def build_lock_wait_graph(*, tool_data: Dict[str, Any]) -> Dict[str, Any]:
    sessions = [item for item in list(tool_data.get("session_status") or []) if isinstance(item, dict)]
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for item in sessions[:12]:
        pid = str(item.get("pid") or item.get("session_id") or item.get("state") or "unknown")
        nodes.append(
            {
                "id": pid,
                "state": str(item.get("state") or ""),
                "wait_event_type": str(item.get("wait_event_type") or ""),
                "wait_event": str(item.get("wait_event") or ""),
            }
        )
        blocker = str(item.get("blocking_pid") or "")
        if blocker:
            edges.append(
                {
                    "from": pid,
                    "to": blocker,
                    "reason": str(item.get("wait_event") or item.get("wait_event_type") or "lock"),
                }
            )
    return {"nodes": nodes[:12], "edges": edges[:12]}
