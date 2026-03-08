"""test LLM 客户端完整日志引用相关测试。"""

import sys
from typing import Any, Dict, List

import pytest

from app.config import settings
from app.core.llm_client import LLMClient
from app.runtime.langgraph.output_truncation import get_output_reference


@pytest.mark.asyncio
async def test_llm_client_emits_full_prompt_and_response_refs(monkeypatch):
    """验证 LLMClient 在调试开关开启时会输出完整 prompt/response ref。"""

    monkeypatch.setattr(settings, "LLM_LOG_FULL_PROMPT", True)
    monkeypatch.setattr(settings, "LLM_LOG_FULL_RESPONSE", True)

    client = LLMClient()
    session = await client.create_session(title="full-log-test")
    events: List[Dict[str, Any]] = []

    async def _trace_callback(event: Dict[str, Any]) -> None:
        events.append(event)

    monkeypatch.setattr(
        client,
        "_run_llm_reply",
        lambda effective_prompt, system_prompt, model_name, agent_name, max_tokens, phase: (
            '{"chat_message":"收到","analysis":"已分析","conclusion":"连接池耗尽","confidence":0.61}'
        ),
    )

    result = await client.send_prompt(
        session.id,
        parts=[{"type": "text", "text": "请总结根因"}],
        agent="ProblemAnalysisAgent",
        trace_callback=_trace_callback,
        trace_context={"phase": "analysis", "stage": "runtime_log_parse", "agent_name": "ProblemAnalysisAgent"},
    )

    assert "连接池耗尽" in str(result.get("content") or "")

    started_event = next(item for item in events if item.get("type") == "llm_call_started")
    response_event = next(item for item in events if item.get("type") == "llm_http_response")

    assert started_event.get("prompt_ref")
    assert response_event.get("response_ref")

    prompt_payload = get_output_reference(str(started_event.get("prompt_ref")))
    response_payload = get_output_reference(str(response_event.get("response_ref")))

    assert prompt_payload and "请总结根因" in str(prompt_payload.get("content") or "")
    assert response_payload and "连接池耗尽" in str(response_payload.get("content") or "")


@pytest.mark.asyncio
async def test_llm_client_writes_full_prompt_and_response_to_logger(monkeypatch):
    """验证调试开关开启后 backend logger 会输出完整 prompt/response。"""

    monkeypatch.setattr(settings, "LLM_LOG_FULL_PROMPT", True)
    monkeypatch.setattr(settings, "LLM_LOG_FULL_RESPONSE", True)

    captured_logs: List[tuple[str, Dict[str, Any]]] = []
    llm_client_module = sys.modules["app.core.llm_client"]

    def _fake_info(event: str, **kwargs: Any) -> None:
        captured_logs.append((event, kwargs))

    monkeypatch.setattr(llm_client_module.logger, "info", _fake_info)

    client = LLMClient()
    session = await client.create_session(title="full-inline-log-test")

    monkeypatch.setattr(
        client,
        "_run_llm_reply",
        lambda effective_prompt, system_prompt, model_name, agent_name, max_tokens, phase: (
            '{"chat_message":"收到","analysis":"已分析","conclusion":"库存锁等待","confidence":0.58}'
        ),
    )

    await client.send_prompt(
        session.id,
        parts=[{"type": "text", "text": "请分析库存锁等待"}],
        agent="DatabaseAgent",
        trace_context={"phase": "analysis", "stage": "database_probe", "agent_name": "DatabaseAgent"},
    )

    prompt_log = next(item for item in captured_logs if item[0] == "llm_request_prompt_full")
    response_log = next(item for item in captured_logs if item[0] == "llm_request_response_full")

    assert "请分析库存锁等待" in str(prompt_log[1].get("prompt_full") or "")
    assert response_log[1].get("response_full")
    assert "库存锁等待" in str(response_log[1].get("response_full") or "")
