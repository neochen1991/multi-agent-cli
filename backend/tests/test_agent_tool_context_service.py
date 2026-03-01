"""Tests for AgentToolContextService edge cases."""

from __future__ import annotations

import subprocess

from app.services.agent_tool_context_service import AgentToolContextService


def test_collect_recent_git_changes_handles_repo_without_commits(tmp_path):
    subprocess.run(
        ["git", "init"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )

    service = AgentToolContextService()
    audit_log = []
    changes = service._collect_recent_git_changes(  # noqa: SLF001 - testing internal fallback behavior
        str(tmp_path),
        20,
        audit_log,
    )

    assert changes == []
    assert any(
        str(item.get("action") or "") == "git_log_changes" and str(item.get("status") or "") == "unavailable"
        for item in audit_log
    )

