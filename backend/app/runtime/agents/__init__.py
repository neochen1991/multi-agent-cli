"""
Agent Factory Module
Agent 工厂模块

提供创建带工具的 LangGraph Agent 的能力。
"""

from app.runtime.agents.config import (
    AgentConfig,
    AGENT_CONFIGS,
    get_agent_config,
    get_all_agent_configs,
    get_agents_by_phase,
    get_enabled_agent_configs,
)
from app.runtime.agents.factory import (
    AgentFactory,
    get_default_factory,
    set_default_factory,
)
from app.runtime.agents.registry import (
    ToolRegistry,
    get_tool,
    get_tools,
    register_tool,
)

__all__ = [
    # Config
    "AgentConfig",
    "AGENT_CONFIGS",
    "get_agent_config",
    "get_all_agent_configs",
    "get_agents_by_phase",
    "get_enabled_agent_configs",
    # Factory
    "AgentFactory",
    "get_default_factory",
    "set_default_factory",
    # ToolRegistry
    "ToolRegistry",
    "get_tool",
    "get_tools",
    "register_tool",
]