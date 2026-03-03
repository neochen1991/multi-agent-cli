"""In-memory tool registry and audit helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.config import settings
from app.runtime.tool_registry.models import ToolPolicy, ToolRegistryItem


class ToolRegistryService:
    def __init__(self) -> None:
        base_paths = [str(Path(settings.LOCAL_STORE_DIR).resolve())]
        self._items: List[ToolRegistryItem] = [
            ToolRegistryItem(
                tool_name="git_repo_search",
                category="repo",
                owner_agent="CodeAgent",
                input_schema={"repo_url": "string", "branch": "string", "keywords": ["string"]},
                policy=ToolPolicy(
                    timeout_seconds=90,
                    audit_level="full",
                    command_whitelist=["git clone", "git fetch", "git log", "git grep"],
                    path_whitelist=base_paths,
                ),
            ),
            ToolRegistryItem(
                tool_name="local_log_reader",
                category="telemetry",
                owner_agent="LogAgent",
                input_schema={"file_path": "string", "max_lines": "int", "keywords": ["string"]},
                policy=ToolPolicy(
                    timeout_seconds=20,
                    audit_level="full",
                    command_whitelist=[],
                    path_whitelist=base_paths,
                ),
            ),
            ToolRegistryItem(
                tool_name="domain_excel_lookup",
                category="asset",
                owner_agent="DomainAgent",
                input_schema={"excel_path": "string", "sheet_name": "string", "max_rows": "int"},
                policy=ToolPolicy(
                    timeout_seconds=20,
                    audit_level="full",
                    command_whitelist=[],
                    path_whitelist=base_paths,
                ),
            ),
            ToolRegistryItem(
                tool_name="runbook_case_library",
                category="ticket",
                owner_agent="RunbookAgent",
                input_schema={"query": "string"},
                policy=ToolPolicy(timeout_seconds=15, audit_level="summary"),
            ),
            ToolRegistryItem(
                tool_name="rule_suggestion_toolkit",
                category="policy",
                owner_agent="RuleSuggestionAgent",
                input_schema={"metrics_signals": ["object"], "runbook_items": ["object"]},
                policy=ToolPolicy(timeout_seconds=20, audit_level="summary"),
            ),
        ]

    async def list_items(self) -> List[Dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self._items]

    async def connectors(self) -> List[Dict[str, Any]]:
        return [
            {"name": "RepoConnector", "resource": "git_repository", "tools": ["git_repo_search", "git_change_window"]},
            {"name": "TelemetryConnector", "resource": "log_file", "tools": ["local_log_reader", "metrics_snapshot_analyzer"]},
            {"name": "AssetConnector", "resource": "domain_excel", "tools": ["domain_excel_lookup"]},
            {"name": "TicketConnector", "resource": "case_library", "tools": ["runbook_case_library"]},
        ]


tool_registry_service = ToolRegistryService()
