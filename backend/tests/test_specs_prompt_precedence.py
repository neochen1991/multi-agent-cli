"""test规格Promptprecedence相关测试。"""

from app.runtime.agents.config import AgentConfig
from app.runtime.langgraph import specs as specs_module


def test_builtin_prompt_has_higher_priority_than_external_config(monkeypatch):
    """验证内置Prompthas更高优先级于外部配置。"""
    
    def fake_get_all_agent_configs():
        """为测试场景提供fakegetallAgentconfigs辅助逻辑。"""
        return {
            "LogAgent": AgentConfig(
                name="LogAgent",
                role="外部角色",
                phase="analysis",
                system_prompt="这是外部覆盖prompt，不应生效",
                tools=["parse_log"],
                max_tokens=777,
                timeout=66,
                temperature=0.3,
                enabled=True,
            )
        }

    monkeypatch.setattr("app.runtime.agents.config.get_all_agent_configs", fake_get_all_agent_configs)
    spec_map = specs_module._build_spec_map()
    log_spec = spec_map["LogAgent"]

    assert "先证据后结论" in log_spec.system_prompt
    assert "外部覆盖prompt" not in log_spec.system_prompt
    assert log_spec.role == "日志分析专家"
    assert log_spec.max_tokens == 777
    assert log_spec.timeout == 66


def test_external_config_can_disable_builtin_agent(monkeypatch):
    """验证外部配置可以禁用内置Agent。"""
    
    def fake_get_all_agent_configs():
        """为测试场景提供fakegetallAgentconfigs辅助逻辑。"""
        return {
            "LogAgent": AgentConfig(
                name="LogAgent",
                role="日志分析专家",
                phase="analysis",
                enabled=False,
            )
        }

    monkeypatch.setattr("app.runtime.agents.config.get_all_agent_configs", fake_get_all_agent_configs)
    spec_map = specs_module._build_spec_map()
    assert "LogAgent" not in spec_map
