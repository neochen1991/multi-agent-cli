"""Tests for agent invoke-path selection in execution helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.config import settings
from app.runtime.langgraph.execution import run_agent_once
from app.runtime.langgraph.state import AgentSpec


class _FakeLLM:
    def __init__(self, *args, **kwargs):
        _ = args, kwargs

    def invoke(self, messages):
        _ = messages
        return SimpleNamespace(content="direct-mode-reply")


class _FakeFactoryAgent:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, payload):
        _ = payload
        return SimpleNamespace(content=self._content)


class _FakeFactory:
    def __init__(self, *, content: str = "", fail: bool = False):
        self._content = content
        self._fail = fail

    def create_agent(self, *args, **kwargs):
        _ = args, kwargs
        if self._fail:
            raise RuntimeError("factory-create-failed")
        return _FakeFactoryAgent(self._content)


class _FakeOrchestrator:
    def __init__(self, factory):
        self._factory = factory

    def _base_url_for_llm(self):
        return "https://unit.test/v3"

    def _agent_http_timeout(self, agent_name: str):
        _ = agent_name
        return 5

    def _get_agent_factory(self):
        return self._factory


def _spec_with_tools() -> AgentSpec:
    return AgentSpec(
        name="LogAgent",
        role="日志分析专家",
        phase="analysis",
        system_prompt="test",
        tools=("read_file",),
    )


def test_run_agent_once_prefers_factory_when_available(monkeypatch):
    monkeypatch.setattr("app.runtime.langgraph.execution.ChatOpenAI", _FakeLLM)
    monkeypatch.setattr(settings, "AGENT_USE_FACTORY", True)
    orchestrator = _FakeOrchestrator(factory=_FakeFactory(content="factory-mode-reply"))

    result = run_agent_once(orchestrator, _spec_with_tools(), "prompt", 256)

    assert result.invoke_mode == "factory"
    assert "factory-mode-reply" in result.content
    assert result.factory_error == ""


def test_run_agent_once_falls_back_to_direct_when_factory_fails(monkeypatch):
    monkeypatch.setattr("app.runtime.langgraph.execution.ChatOpenAI", _FakeLLM)
    monkeypatch.setattr(settings, "AGENT_USE_FACTORY", True)
    orchestrator = _FakeOrchestrator(factory=_FakeFactory(fail=True))

    result = run_agent_once(orchestrator, _spec_with_tools(), "prompt", 256)

    assert result.invoke_mode == "direct"
    assert "direct-mode-reply" in result.content
    assert "factory-create-failed" in result.factory_error


def test_run_agent_once_uses_direct_when_factory_disabled(monkeypatch):
    monkeypatch.setattr("app.runtime.langgraph.execution.ChatOpenAI", _FakeLLM)
    monkeypatch.setattr(settings, "AGENT_USE_FACTORY", False)
    orchestrator = _FakeOrchestrator(factory=_FakeFactory(content="factory-mode-reply"))

    result = run_agent_once(orchestrator, _spec_with_tools(), "prompt", 256)

    assert result.invoke_mode == "direct"
    assert "direct-mode-reply" in result.content
