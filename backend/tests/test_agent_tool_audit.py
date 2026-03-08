"""testAgent工具audit相关测试。"""

from app.services.agent_tool_context_service import AgentToolContextService


def test_audit_record_contains_call_id_and_summaries():
    """验证auditrecord包含调用IDand摘要。"""
    
    service = AgentToolContextService()
    row = service._audit(  # noqa: SLF001 - unit test internal contract
        tool_name="git_repo_search",
        action="repo_search",
        status="ok",
        detail={
            "repo_url": "https://example.com/repo.git",
            "keywords": ["orders", "timeout"],
            "hits_count": 3,
            "duration_ms": 12.3,
        },
    )

    assert str(row.get("call_id") or "").startswith("git_repo_search_repo_search_")
    assert "repo_url=" in str(row.get("request_summary") or "")
    assert "hits_count=3" in str(row.get("response_summary") or "")
    assert row.get("duration_ms") == 12.3
