"""testAgent规格相关测试。"""

import pytest

from app.runtime.langgraph.state import AgentSpec
from app.runtime.agents.config import AgentConfig, get_agent_config, get_all_agent_configs


class TestAgentSpec:
    """归档AgentSpec相关测试场景。"""

    def test_create_basic_spec(self):
        """验证创建basic规格。"""
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
        """验证创建规格带allfields。"""
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
        """验证规格isfrozen。"""
        spec = AgentSpec(
            name="TestAgent",
            role="Test Role",
            phase="analysis",
            system_prompt="Test prompt",
        )

        with pytest.raises(AttributeError):
            spec.name = "NewName"

    def test_from_config(self):
        """验证从配置。"""
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
        """验证从配置invalidtype。"""
        with pytest.raises(TypeError):
            AgentSpec.from_config({"name": "Test"})


class TestAgentConfig:
    """归档AgentConfig相关测试场景。"""

    def test_create_basic_config(self):
        """验证创建basic配置。"""
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
        """验证todict。"""
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
        """验证to规格。"""
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
        """验证从dict。"""
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
    """归档AgentConfigs相关测试场景。"""

    def test_get_agent_config_existing(self):
        """验证getAgent配置existing。"""
        config = get_agent_config("LogAgent")

        assert config is not None
        assert config.name == "LogAgent"
        assert config.role == "日志分析专家"
        assert config.phase == "analysis"

    def test_get_agent_config_nonexistent(self):
        """验证getAgent配置nonexistent。"""
        config = get_agent_config("NonExistentAgent")

        assert config is None

    def test_get_all_agent_configs(self):
        """验证getallAgentconfigs。"""
        configs = get_all_agent_configs()

        assert "LogAgent" in configs
        assert "CodeAgent" in configs
        assert "DomainAgent" in configs
        assert "CriticAgent" in configs
        assert "RebuttalAgent" in configs
        assert "JudgeAgent" in configs
        assert "ProblemAnalysisAgent" in configs

    def test_log_agent_has_tools(self):
        """验证logAgenthas工具。"""
        config = get_agent_config("LogAgent")

        assert config is not None
        assert len(config.tools) > 0
        assert "parse_log" in config.tools

    def test_judge_agent_no_tools(self):
        """验证裁决Agent无工具。"""
        config = get_agent_config("JudgeAgent")

        assert config is not None
        assert config.tools == []
        assert config.max_tokens == 900  # JudgeAgent has larger token limit
