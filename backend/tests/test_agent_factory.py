"""testAgent工厂相关测试。"""

import pytest
from unittest.mock import MagicMock, patch

from app.runtime.agents import (
    AgentFactory,
    AgentConfig,
    AGENT_CONFIGS,
    get_agent_config,
    get_all_agent_configs,
    get_agents_by_phase,
    get_enabled_agent_configs,
    get_default_factory,
    set_default_factory,
)


class TestAgentConfig:
    """归档AgentConfig相关测试场景。"""

    def test_create_config(self):
        """验证创建配置。"""
        config = AgentConfig(
            name="LogAgent",
            role="日志分析专家",
            phase="analysis",
            tools=["parse_log", "read_file"],
            max_tokens=320,
            timeout=35,
        )

        assert config.name == "LogAgent"
        assert config.role == "日志分析专家"
        assert config.phase == "analysis"
        assert config.tools == ["parse_log", "read_file"]
        assert config.max_tokens == 320
        assert config.timeout == 35
        assert config.enabled is True

    def test_to_dict(self):
        """验证todict。"""
        config = AgentConfig(
            name="LogAgent",
            role="日志分析专家",
            phase="analysis",
            tools=["parse_log"],
        )

        result = config.to_dict()

        assert result["name"] == "LogAgent"
        assert result["role"] == "日志分析专家"
        assert result["phase"] == "analysis"
        assert result["tools"] == ["parse_log"]

    def test_from_dict(self):
        """验证从dict。"""
        data = {
            "name": "CodeAgent",
            "role": "代码分析专家",
            "phase": "analysis",
            "tools": ["git_tool", "read_file"],
            "max_tokens": 420,
            "timeout": 40,
        }

        config = AgentConfig.from_dict(data)

        assert config.name == "CodeAgent"
        assert config.role == "代码分析专家"
        assert config.max_tokens == 420


class TestAgentConfigs:
    """归档AgentConfigs相关测试场景。"""

    def test_log_agent_config_exists(self):
        """验证logAgent配置exists。"""
        assert "LogAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["LogAgent"]
        assert config["phase"] == "analysis"
        assert "parse_log" in config["tools"]

    def test_code_agent_config_exists(self):
        """验证codeAgent配置exists。"""
        assert "CodeAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["CodeAgent"]
        assert config["phase"] == "analysis"
        assert "git_tool" in config["tools"]

    def test_judge_agent_config_exists(self):
        """验证裁决Agent配置exists。"""
        assert "JudgeAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["JudgeAgent"]
        assert config["phase"] == "judgment"
        assert config["tools"] == []  # Judge has no tools

    def test_critic_agent_config_exists(self):
        """验证质疑Agent配置exists。"""
        assert "CriticAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["CriticAgent"]
        assert config["phase"] == "critique"

    def test_rebuttal_agent_config_exists(self):
        """验证反驳Agent配置exists。"""
        assert "RebuttalAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["RebuttalAgent"]
        assert config["phase"] == "rebuttal"

    def test_domain_agent_config_exists(self):
        """验证domainAgent配置exists。"""
        assert "DomainAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["DomainAgent"]
        assert config["phase"] == "analysis"
        assert "ddd_analyzer" in config["tools"]


class TestGetAgentConfig:
    """归档GetAgentConfig相关测试场景。"""

    def test_returns_config_for_existing_agent(self):
        """验证返回配置forexistingAgent。"""
        config = get_agent_config("LogAgent")

        assert config is not None
        assert config.name == "LogAgent"
        assert config.phase == "analysis"

    def test_returns_none_for_nonexistent_agent(self):
        """验证返回nonefornonexistentAgent。"""
        config = get_agent_config("NonExistentAgent")

        assert config is None


class TestGetAllAgentConfigs:
    """归档GetAllAgentConfigs相关测试场景。"""

    def test_returns_all_configs(self):
        """验证返回allconfigs。"""
        configs = get_all_agent_configs()

        assert len(configs) == len(AGENT_CONFIGS)
        assert "LogAgent" in configs
        assert "CodeAgent" in configs
        assert "JudgeAgent" in configs


class TestGetAgentsByPhase:
    """归档GetAgentsByPhase相关测试场景。"""

    def test_returns_analysis_agents(self):
        """验证返回分析Agent。"""
        agents = get_agents_by_phase("analysis")

        agent_names = [a.name for a in agents]
        assert "LogAgent" in agent_names
        assert "CodeAgent" in agent_names
        assert "DomainAgent" in agent_names

    def test_returns_critique_agents(self):
        """验证返回critiqueAgent。"""
        agents = get_agents_by_phase("critique")

        agent_names = [a.name for a in agents]
        assert "CriticAgent" in agent_names

    def test_returns_judgment_agents(self):
        """验证返回judgmentAgent。"""
        agents = get_agents_by_phase("judgment")

        agent_names = [a.name for a in agents]
        assert "JudgeAgent" in agent_names

    def test_returns_empty_for_unknown_phase(self):
        """验证返回空forunknownphase。"""
        agents = get_agents_by_phase("unknown_phase")

        assert agents == []


class TestAgentFactory:
    """归档AgentFactory相关测试场景。"""

    def test_factory_initialization(self):
        """验证工厂initialization。"""
        factory = AgentFactory()

        assert factory._llm is None
        assert factory._default_tools == []

    def test_factory_with_llm(self):
        """验证工厂带LLM。"""
        mock_llm = MagicMock()
        factory = AgentFactory(llm=mock_llm)

        assert factory._llm == mock_llm

    def test_set_llm_clears_cache(self):
        """验证setLLMclearscache。"""
        factory = AgentFactory()
        factory._agent_cache["test"] = MagicMock()

        mock_llm = MagicMock()
        factory.set_llm(mock_llm)

        assert factory._llm == mock_llm
        assert len(factory._agent_cache) == 0

    def test_create_agent_requires_llm(self):
        """验证创建AgentrequiresLLM。"""
        factory = AgentFactory()

        with pytest.raises(ValueError, match="No LLM provided"):
            factory.create_agent("LogAgent")

    def test_create_agent_unknown_name(self):
        """验证创建Agentunknownname。"""
        factory = AgentFactory()

        mock_llm = MagicMock()
        with pytest.raises(ValueError, match="Unknown agent"):
            factory.create_agent("UnknownAgent", llm=mock_llm)

    def test_resolve_tools_from_strings(self):
        """验证resolve工具从strings。"""
        factory = AgentFactory()

        # Test that _resolve_tools converts string tool names
        # This is an indirect test via checking the method exists
        assert hasattr(factory, '_resolve_tools')

    def test_clear_cache(self):
        """验证clearcache。"""
        factory = AgentFactory()
        factory._agent_cache["test1"] = MagicMock()
        factory._agent_cache["test2"] = MagicMock()

        factory.clear_cache()

        assert len(factory._agent_cache) == 0


class TestFactorySingleton:
    """归档FactorySingleton相关测试场景。"""

    def test_get_default_factory(self):
        """验证get默认工厂。"""
        factory = get_default_factory()

        assert factory is not None
        assert isinstance(factory, AgentFactory)

    def test_set_default_factory(self):
        """验证set默认工厂。"""
        new_factory = AgentFactory()
        set_default_factory(new_factory)

        result = get_default_factory()
        assert result == new_factory


class TestAgentToolBinding:
    """归档AgentToolBinding相关测试场景。"""

    def test_log_agent_has_file_tools(self):
        """验证logAgenthasfile工具。"""
        config = get_agent_config("LogAgent")

        assert "parse_log" in config.tools
        assert "read_file" in config.tools
        assert "search_in_files" in config.tools

    def test_code_agent_has_git_tools(self):
        """验证codeAgenthasGit工具。"""
        config = get_agent_config("CodeAgent")

        assert "git_tool" in config.tools
        assert "read_file" in config.tools
        assert "search_in_files" in config.tools
        assert "list_files" in config.tools

    def test_judge_agent_has_no_tools(self):
        """验证裁决Agenthas无工具。"""
        config = get_agent_config("JudgeAgent")

        assert config.tools == []


class TestAgentTokenLimits:
    """归档AgentTokenLimits相关测试场景。"""

    def test_judge_has_higher_token_limit(self):
        """验证裁决has更高tokenlimit。"""
        judge_config = get_agent_config("JudgeAgent")
        log_config = get_agent_config("LogAgent")

        assert judge_config.max_tokens > log_config.max_tokens

    def test_judge_has_longer_timeout(self):
        """验证裁决haslonger超时。"""
        judge_config = get_agent_config("JudgeAgent")
        log_config = get_agent_config("LogAgent")

        assert judge_config.timeout > log_config.timeout

    def test_all_agents_have_valid_limits(self):
        """验证allAgenthavevalidlimits。"""
        for name, config_dict in AGENT_CONFIGS.items():
            config = AgentConfig.from_dict(config_dict)

            assert config.max_tokens > 0, f"{name} should have positive max_tokens"
            assert config.max_tokens < 2000, f"{name} max_tokens seems too high"
            assert config.timeout > 0, f"{name} should have positive timeout"
            assert config.timeout < 300, f"{name} timeout seems too high"
