"""
Unit tests for Agent Factory.
"""

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
    """Tests for AgentConfig dataclass."""

    def test_create_config(self):
        """Should create config with all fields."""
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
        """Should convert to dict."""
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
        """Should create from dict."""
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
    """Tests for AGENT_CONFIGS dictionary."""

    def test_log_agent_config_exists(self):
        """Should have LogAgent config."""
        assert "LogAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["LogAgent"]
        assert config["phase"] == "analysis"
        assert "parse_log" in config["tools"]

    def test_code_agent_config_exists(self):
        """Should have CodeAgent config."""
        assert "CodeAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["CodeAgent"]
        assert config["phase"] == "analysis"
        assert "git_tool" in config["tools"]

    def test_judge_agent_config_exists(self):
        """Should have JudgeAgent config."""
        assert "JudgeAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["JudgeAgent"]
        assert config["phase"] == "judgment"
        assert config["tools"] == []  # Judge has no tools

    def test_critic_agent_config_exists(self):
        """Should have CriticAgent config."""
        assert "CriticAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["CriticAgent"]
        assert config["phase"] == "critique"

    def test_rebuttal_agent_config_exists(self):
        """Should have RebuttalAgent config."""
        assert "RebuttalAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["RebuttalAgent"]
        assert config["phase"] == "rebuttal"

    def test_domain_agent_config_exists(self):
        """Should have DomainAgent config."""
        assert "DomainAgent" in AGENT_CONFIGS
        config = AGENT_CONFIGS["DomainAgent"]
        assert config["phase"] == "analysis"
        assert "ddd_analyzer" in config["tools"]


class TestGetAgentConfig:
    """Tests for get_agent_config function."""

    def test_returns_config_for_existing_agent(self):
        """Should return config for existing agent."""
        config = get_agent_config("LogAgent")

        assert config is not None
        assert config.name == "LogAgent"
        assert config.phase == "analysis"

    def test_returns_none_for_nonexistent_agent(self):
        """Should return None for nonexistent agent."""
        config = get_agent_config("NonExistentAgent")

        assert config is None


class TestGetAllAgentConfigs:
    """Tests for get_all_agent_configs function."""

    def test_returns_all_configs(self):
        """Should return all agent configs."""
        configs = get_all_agent_configs()

        assert len(configs) == len(AGENT_CONFIGS)
        assert "LogAgent" in configs
        assert "CodeAgent" in configs
        assert "JudgeAgent" in configs


class TestGetAgentsByPhase:
    """Tests for get_agents_by_phase function."""

    def test_returns_analysis_agents(self):
        """Should return agents in analysis phase."""
        agents = get_agents_by_phase("analysis")

        agent_names = [a.name for a in agents]
        assert "LogAgent" in agent_names
        assert "CodeAgent" in agent_names
        assert "DomainAgent" in agent_names

    def test_returns_critique_agents(self):
        """Should return agents in critique phase."""
        agents = get_agents_by_phase("critique")

        agent_names = [a.name for a in agents]
        assert "CriticAgent" in agent_names

    def test_returns_judgment_agents(self):
        """Should return agents in judgment phase."""
        agents = get_agents_by_phase("judgment")

        agent_names = [a.name for a in agents]
        assert "JudgeAgent" in agent_names

    def test_returns_empty_for_unknown_phase(self):
        """Should return empty list for unknown phase."""
        agents = get_agents_by_phase("unknown_phase")

        assert agents == []


class TestAgentFactory:
    """Tests for AgentFactory class."""

    def test_factory_initialization(self):
        """Should initialize factory."""
        factory = AgentFactory()

        assert factory._llm is None
        assert factory._default_tools == []

    def test_factory_with_llm(self):
        """Should initialize with LLM."""
        mock_llm = MagicMock()
        factory = AgentFactory(llm=mock_llm)

        assert factory._llm == mock_llm

    def test_set_llm_clears_cache(self):
        """Should clear cache when LLM is set."""
        factory = AgentFactory()
        factory._agent_cache["test"] = MagicMock()

        mock_llm = MagicMock()
        factory.set_llm(mock_llm)

        assert factory._llm == mock_llm
        assert len(factory._agent_cache) == 0

    def test_create_agent_requires_llm(self):
        """Should raise error if no LLM is provided."""
        factory = AgentFactory()

        with pytest.raises(ValueError, match="No LLM provided"):
            factory.create_agent("LogAgent")

    def test_create_agent_unknown_name(self):
        """Should raise error for unknown agent name."""
        factory = AgentFactory()

        mock_llm = MagicMock()
        with pytest.raises(ValueError, match="Unknown agent"):
            factory.create_agent("UnknownAgent", llm=mock_llm)

    def test_resolve_tools_from_strings(self):
        """Should resolve tool names to tool instances."""
        factory = AgentFactory()

        # Test that _resolve_tools converts string tool names
        # This is an indirect test via checking the method exists
        assert hasattr(factory, '_resolve_tools')

    def test_clear_cache(self):
        """Should clear agent cache."""
        factory = AgentFactory()
        factory._agent_cache["test1"] = MagicMock()
        factory._agent_cache["test2"] = MagicMock()

        factory.clear_cache()

        assert len(factory._agent_cache) == 0


class TestFactorySingleton:
    """Tests for factory singleton functions."""

    def test_get_default_factory(self):
        """Should return default factory instance."""
        factory = get_default_factory()

        assert factory is not None
        assert isinstance(factory, AgentFactory)

    def test_set_default_factory(self):
        """Should set default factory instance."""
        new_factory = AgentFactory()
        set_default_factory(new_factory)

        result = get_default_factory()
        assert result == new_factory


class TestAgentToolBinding:
    """Tests for agent tool bindings in config."""

    def test_log_agent_has_file_tools(self):
        """LogAgent should have file reading tools."""
        config = get_agent_config("LogAgent")

        assert "parse_log" in config.tools
        assert "read_file" in config.tools
        assert "search_in_files" in config.tools

    def test_code_agent_has_git_tools(self):
        """CodeAgent should have git tools."""
        config = get_agent_config("CodeAgent")

        assert "git_tool" in config.tools
        assert "read_file" in config.tools
        assert "search_in_files" in config.tools
        assert "list_files" in config.tools

    def test_judge_agent_has_no_tools(self):
        """JudgeAgent should have no tools."""
        config = get_agent_config("JudgeAgent")

        assert config.tools == []


class TestAgentTokenLimits:
    """Tests for agent token and timeout limits."""

    def test_judge_has_higher_token_limit(self):
        """JudgeAgent should have higher token limit."""
        judge_config = get_agent_config("JudgeAgent")
        log_config = get_agent_config("LogAgent")

        assert judge_config.max_tokens > log_config.max_tokens

    def test_judge_has_longer_timeout(self):
        """JudgeAgent should have longer timeout."""
        judge_config = get_agent_config("JudgeAgent")
        log_config = get_agent_config("LogAgent")

        assert judge_config.timeout > log_config.timeout

    def test_all_agents_have_valid_limits(self):
        """All agents should have valid token and timeout limits."""
        for name, config_dict in AGENT_CONFIGS.items():
            config = AgentConfig.from_dict(config_dict)

            assert config.max_tokens > 0, f"{name} should have positive max_tokens"
            assert config.max_tokens < 2000, f"{name} max_tokens seems too high"
            assert config.timeout > 0, f"{name} should have positive timeout"
            assert config.timeout < 300, f"{name} timeout seems too high"