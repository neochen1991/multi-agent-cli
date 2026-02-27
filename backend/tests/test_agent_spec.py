"""
Unit tests for AgentSpec and AgentConfig.
"""

import pytest

from app.runtime.langgraph.state import AgentSpec
from app.runtime.agents.config import AgentConfig, get_agent_config, get_all_agent_configs


class TestAgentSpec:
    """Tests for AgentSpec dataclass."""

    def test_create_basic_spec(self):
        """Should create AgentSpec with basic fields."""
        spec = AgentSpec(
            name="TestAgent",
            role="Test Role",
            phase="analysis",
            system_prompt="Test prompt",
        )

        assert spec.name == "TestAgent"
        assert spec.role == "Test Role"
        assert spec.phase == "analysis"
        assert spec.system_prompt == "Test prompt"
        assert spec.tools == ()
        assert spec.max_tokens == 320
        assert spec.timeout == 35
        assert spec.temperature == 0.15

    def test_create_spec_with_all_fields(self):
        """Should create AgentSpec with all fields."""
        spec = AgentSpec(
            name="TestAgent",
            role="Test Role",
            phase="analysis",
            system_prompt="Test prompt",
            tools=("tool1", "tool2"),
            max_tokens=500,
            timeout=60,
            temperature=0.3,
        )

        assert spec.tools == ("tool1", "tool2")
        assert spec.max_tokens == 500
        assert spec.timeout == 60
        assert spec.temperature == 0.3

    def test_spec_is_frozen(self):
        """AgentSpec should be immutable (frozen)."""
        spec = AgentSpec(
            name="TestAgent",
            role="Test Role",
            phase="analysis",
            system_prompt="Test prompt",
        )

        with pytest.raises(AttributeError):
            spec.name = "NewName"

    def test_from_config(self):
        """Should create AgentSpec from AgentConfig."""
        config = AgentConfig(
            name="LogAgent",
            role="日志分析专家",
            phase="analysis",
            system_prompt="你是日志分析专家",
            tools=["parse_log", "read_file"],
            max_tokens=320,
            timeout=35,
            temperature=0.15,
        )

        spec = AgentSpec.from_config(config)

        assert spec.name == "LogAgent"
        assert spec.role == "日志分析专家"
        assert spec.phase == "analysis"
        assert spec.system_prompt == "你是日志分析专家"
        assert spec.tools == ("parse_log", "read_file")
        assert spec.max_tokens == 320

    def test_from_config_invalid_type(self):
        """Should raise TypeError for invalid config type."""
        with pytest.raises(TypeError):
            AgentSpec.from_config({"name": "Test"})


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_create_basic_config(self):
        """Should create AgentConfig with basic fields."""
        config = AgentConfig(
            name="TestAgent",
            role="Test Role",
            phase="analysis",
        )

        assert config.name == "TestAgent"
        assert config.role == "Test Role"
        assert config.phase == "analysis"
        assert config.system_prompt is None
        assert config.tools == []
        assert config.max_tokens == 320
        assert config.timeout == 35
        assert config.temperature == 0.15
        assert config.enabled is True

    def test_to_dict(self):
        """Should convert AgentConfig to dict."""
        config = AgentConfig(
            name="TestAgent",
            role="Test Role",
            phase="analysis",
            system_prompt="Test prompt",
            tools=["tool1"],
        )

        result = config.to_dict()

        assert result["name"] == "TestAgent"
        assert result["role"] == "Test Role"
        assert result["phase"] == "analysis"
        assert result["system_prompt"] == "Test prompt"
        assert result["tools"] == ["tool1"]

    def test_to_spec(self):
        """Should convert AgentConfig to AgentSpec."""
        config = AgentConfig(
            name="LogAgent",
            role="日志分析专家",
            phase="analysis",
            system_prompt="你是日志分析专家",
            tools=["parse_log"],
            max_tokens=400,
        )

        spec = config.to_spec()

        assert isinstance(spec, AgentSpec)
        assert spec.name == "LogAgent"
        assert spec.role == "日志分析专家"
        assert spec.tools == ("parse_log",)
        assert spec.max_tokens == 400

    def test_from_dict(self):
        """Should create AgentConfig from dict."""
        data = {
            "name": "LogAgent",
            "role": "日志分析专家",
            "phase": "analysis",
            "system_prompt": "Test prompt",
            "tools": ["tool1", "tool2"],
            "max_tokens": 500,
        }

        config = AgentConfig.from_dict(data)

        assert config.name == "LogAgent"
        assert config.role == "日志分析专家"
        assert config.tools == ["tool1", "tool2"]
        assert config.max_tokens == 500


class TestAgentConfigs:
    """Tests for agent configuration functions."""

    def test_get_agent_config_existing(self):
        """Should get existing agent config."""
        config = get_agent_config("LogAgent")

        assert config is not None
        assert config.name == "LogAgent"
        assert config.role == "日志分析专家"
        assert config.phase == "analysis"

    def test_get_agent_config_nonexistent(self):
        """Should return None for nonexistent agent."""
        config = get_agent_config("NonExistentAgent")

        assert config is None

    def test_get_all_agent_configs(self):
        """Should get all agent configs."""
        configs = get_all_agent_configs()

        assert "LogAgent" in configs
        assert "CodeAgent" in configs
        assert "DomainAgent" in configs
        assert "CriticAgent" in configs
        assert "RebuttalAgent" in configs
        assert "JudgeAgent" in configs
        assert "ProblemAnalysisAgent" in configs

    def test_log_agent_has_tools(self):
        """LogAgent should have tools configured."""
        config = get_agent_config("LogAgent")

        assert config is not None
        assert len(config.tools) > 0
        assert "parse_log" in config.tools

    def test_judge_agent_no_tools(self):
        """JudgeAgent should have no tools."""
        config = get_agent_config("JudgeAgent")

        assert config is not None
        assert config.tools == []
        assert config.max_tokens == 900  # JudgeAgent has larger token limit