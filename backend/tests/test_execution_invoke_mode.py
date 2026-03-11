"""testexecutioninvoke模式相关测试。"""

from __future__ import annotations

from types import SimpleNamespace

from app.config import settings
from app.runtime.langgraph.execution import run_agent_once
from app.runtime.langgraph.state import AgentSpec


class _FakeLLM:
    """为测试场景提供FakeLLM辅助对象。"""
    last_kwargs = None

    def __init__(self, *args, **kwargs):
        """为测试场景提供init辅助逻辑。"""

        _ = args
        type(self).last_kwargs = kwargs

    def invoke(self, messages):
        """为测试场景提供invoke辅助逻辑。"""
        
        _ = messages
        return SimpleNamespace(content="direct-mode-reply")


class _FakeFactoryAgent:
    """为测试场景提供FakeFactoryAgent辅助对象。"""
    
    def __init__(self, content: str):
        """为测试场景提供init辅助逻辑。"""
        
        self._content = content

    def invoke(self, payload):
        """为测试场景提供invoke辅助逻辑。"""
        
        _ = payload
        return SimpleNamespace(content=self._content)


class _FakeFactory:
    """为测试场景提供FakeFactory辅助对象。"""
    
    def __init__(self, *, content: str = "", fail: bool = False):
        """为测试场景提供init辅助逻辑。"""
        
        self._content = content
        self._fail = fail

    def create_agent(self, *args, **kwargs):
        """为测试场景提供创建Agent辅助逻辑。"""
        
        _ = args, kwargs
        if self._fail:
            raise RuntimeError("factory-create-failed")
        return _FakeFactoryAgent(self._content)


class _FakeOrchestrator:
    """为测试场景提供FakeOrchestrator辅助对象。"""
    
    def __init__(self, factory):
        """为测试场景提供init辅助逻辑。"""
        
        self._factory = factory

    def _base_url_for_llm(self):
        """为测试场景提供baseurlforLLM辅助逻辑。"""
        
        return "https://unit.test/v3"

    def _agent_http_timeout(self, agent_name: str):
        """为测试场景提供AgentHTTP超时辅助逻辑。"""
        
        _ = agent_name
        return 5

    def _get_agent_factory(self):
        """为测试场景提供getAgent工厂辅助逻辑。"""
        
        return self._factory


def _spec_with_tools() -> AgentSpec:
    """为测试场景提供规格带工具辅助逻辑。"""
    
    return AgentSpec(
        name="LogAgent",
        role="日志分析专家",
        phase="analysis",
        system_prompt="test",
        tools=("read_file",),
    )


def test_run_agent_once_uses_direct_even_when_factory_is_available(monkeypatch):
    """run_agent_once 现在是纯 direct 入口，不再承担 factory 分支。"""

    monkeypatch.setattr("app.runtime.langgraph.execution.ChatOpenAI", _FakeLLM)
    monkeypatch.setattr(settings, "AGENT_USE_FACTORY", True)
    orchestrator = _FakeOrchestrator(factory=_FakeFactory(content="factory-mode-reply"))

    result = run_agent_once(orchestrator, _spec_with_tools(), "prompt", 256)

    assert result.invoke_mode == "direct"
    assert "direct-mode-reply" in result.content


def test_run_agent_once_falls_back_to_direct_when_factory_fails(monkeypatch):
    """即使外部 factory 不可用，direct 入口也应保持可执行。"""

    monkeypatch.setattr("app.runtime.langgraph.execution.ChatOpenAI", _FakeLLM)
    monkeypatch.setattr(settings, "AGENT_USE_FACTORY", True)
    orchestrator = _FakeOrchestrator(factory=_FakeFactory(fail=True))

    result = run_agent_once(orchestrator, _spec_with_tools(), "prompt", 256)

    assert result.invoke_mode == "direct"
    assert "direct-mode-reply" in result.content


def test_run_agent_once_uses_direct_when_factory_disabled(monkeypatch):
    """验证runAgentonce使用direct当工厂禁用。"""
    
    monkeypatch.setattr("app.runtime.langgraph.execution.ChatOpenAI", _FakeLLM)
    monkeypatch.setattr(settings, "AGENT_USE_FACTORY", False)
    orchestrator = _FakeOrchestrator(factory=_FakeFactory(content="factory-mode-reply"))

    result = run_agent_once(orchestrator, _spec_with_tools(), "prompt", 256)

    assert result.invoke_mode == "direct"
    assert "direct-mode-reply" in result.content


def test_run_agent_once_passes_extra_body_explicitly(monkeypatch):
    """direct 模式应显式传 extra_body，避免 LangChain 运行时 warning。"""

    _FakeLLM.last_kwargs = None
    monkeypatch.setattr("app.runtime.langgraph.execution.ChatOpenAI", _FakeLLM)
    monkeypatch.setattr(settings, "AGENT_USE_FACTORY", False)
    orchestrator = _FakeOrchestrator(factory=_FakeFactory(content="factory-mode-reply"))

    result = run_agent_once(orchestrator, _spec_with_tools(), "prompt", 256)

    assert result.invoke_mode == "direct"
    assert _FakeLLM.last_kwargs is not None
    assert _FakeLLM.last_kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}
    assert "model_kwargs" not in _FakeLLM.last_kwargs
