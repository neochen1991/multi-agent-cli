import os

import pytest

from app.core.llm_client import get_llm_client


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_live_llm_minimal_roundtrip():
    if os.getenv("RUN_LIVE_LLM_TESTS", "0") != "1":
        pytest.skip("set RUN_LIVE_LLM_TESTS=1 to enable live LLM regression tests")
    if not os.getenv("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY is required for live LLM regression tests")

    client = get_llm_client()
    session = await client.create_session(title="live_regression")
    result = await client.send_prompt(
        session_id=session.id,
        parts=[{"type": "text", "text": "请仅返回一个 JSON：{\"ok\": true}"}],
        format={
            "type": "json_schema",
            "schema": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            },
        },
        max_tokens=120,
        use_session_history=False,
    )

    assert isinstance(result, dict)
    assert isinstance(result.get("content"), str) and result["content"].strip()
    structured = result.get("structured") or {}
    assert structured.get("ok") is True
