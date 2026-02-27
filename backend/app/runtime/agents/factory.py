"""
Agent Factory
Agent 工厂

使用 LangGraph prebuilt 创建带工具的 Agent。
支持动态工具绑定和自定义系统提示。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union, TYPE_CHECKING

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool as LCBaseTool
from langgraph.prebuilt import create_react_agent

# Use TYPE_CHECKING to avoid runtime import issues with CompiledGraph
if TYPE_CHECKING:
    from langgraph.pregel import Pregel as CompiledGraph

from app.runtime.agents.config import AgentConfig, AGENT_CONFIGS, get_agent_config
from app.runtime.agents.registry import ToolRegistry
from app.tools.langchain_tools import get_tools, get_tool

logger = structlog.get_logger()


class AgentFactory:
    """
    Agent 工厂类

    负责创建带工具的 LangGraph Agent 实例。
    使用 LangGraph 的 create_react_agent 构建 ReAct 模式的 Agent。
    """

    def __init__(
        self,
        llm: Optional[BaseChatModel] = None,
        default_tools: Optional[List[LCBaseTool]] = None,
    ):
        """
        初始化 Agent 工厂。

        Args:
            llm: 默认使用的 LLM 模型
            default_tools: 所有 Agent 默认可用的工具列表
        """
        self._llm = llm
        self._default_tools = default_tools or []
        self._agent_cache: Dict[str, CompiledGraph] = {}

    def set_llm(self, llm: BaseChatModel) -> None:
        """设置默认 LLM 模型"""
        self._llm = llm
        self._agent_cache.clear()  # 清除缓存，因为 LLM 变化了

    def set_default_tools(self, tools: List[LCBaseTool]) -> None:
        """设置默认工具列表"""
        self._default_tools = tools
        self._agent_cache.clear()

    def create_agent(
        self,
        name: str,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[Union[str, LCBaseTool]]] = None,
        system_prompt: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        **kwargs,
    ) -> CompiledGraph:
        """
        创建指定名称的 Agent。

        Args:
            name: Agent 名称（如 "LogAgent", "CodeAgent"）
            llm: 使用的 LLM 模型，不指定则使用工厂默认
            tools: 工具列表（可以是工具名称字符串或工具实例）
            system_prompt: 自定义系统提示
            config: 自定义配置（优先级高于默认配置）
            **kwargs: 其他传递给 create_react_agent 的参数

        Returns:
            编译后的 LangGraph Agent
        """
        # 检查缓存
        cache_key = self._get_cache_key(name, llm, tools, system_prompt)
        if cache_key in self._agent_cache:
            logger.debug("agent_cache_hit", name=name)
            return self._agent_cache[cache_key]

        # 获取配置
        agent_config = config or get_agent_config(name)
        if not agent_config:
            raise ValueError(f"Unknown agent: {name}")

        # 确定 LLM
        model = llm or self._llm
        if model is None:
            raise ValueError("No LLM provided. Set a default LLM or pass one explicitly.")

        # 解析工具
        resolved_tools = self._resolve_tools(tools, agent_config.tools)

        # 确定系统提示
        prompt = system_prompt or agent_config.system_prompt or self._build_default_prompt(agent_config)

        # 创建 state_modifier
        state_modifier = self._build_state_modifier(prompt, agent_config)

        # 创建 Agent
        agent = create_react_agent(
            model=model,
            tools=resolved_tools,
            state_modifier=state_modifier,
            **kwargs,
        )

        # 缓存
        self._agent_cache[cache_key] = agent
        logger.info(
            "agent_created",
            name=name,
            tools_count=len(resolved_tools),
            max_tokens=agent_config.max_tokens,
        )

        return agent

    def create_log_agent(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[Union[str, LCBaseTool]]] = None,
        **kwargs,
    ) -> CompiledGraph:
        """创建日志分析 Agent"""
        return self.create_agent("LogAgent", llm=llm, tools=tools, **kwargs)

    def create_code_agent(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[Union[str, LCBaseTool]]] = None,
        **kwargs,
    ) -> CompiledGraph:
        """创建代码分析 Agent"""
        return self.create_agent("CodeAgent", llm=llm, tools=tools, **kwargs)

    def create_domain_agent(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[Union[str, LCBaseTool]]] = None,
        **kwargs,
    ) -> CompiledGraph:
        """创建领域映射 Agent"""
        return self.create_agent("DomainAgent", llm=llm, tools=tools, **kwargs)

    def create_critic_agent(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[Union[str, LCBaseTool]]] = None,
        **kwargs,
    ) -> CompiledGraph:
        """创建架构质疑 Agent"""
        return self.create_agent("CriticAgent", llm=llm, tools=tools, **kwargs)

    def create_rebuttal_agent(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[Union[str, LCBaseTool]]] = None,
        **kwargs,
    ) -> CompiledGraph:
        """创建技术反驳 Agent"""
        return self.create_agent("RebuttalAgent", llm=llm, tools=tools, **kwargs)

    def create_judge_agent(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[Union[str, LCBaseTool]]] = None,
        **kwargs,
    ) -> CompiledGraph:
        """创建裁决 Agent"""
        return self.create_agent("JudgeAgent", llm=llm, tools=tools, **kwargs)

    def create_commander_agent(
        self,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[Union[str, LCBaseTool]]] = None,
        **kwargs,
    ) -> CompiledGraph:
        """创建问题分析协调 Agent"""
        return self.create_agent("ProblemAnalysisAgent", llm=llm, tools=tools, **kwargs)

    def create_all_agents(
        self,
        llm: Optional[BaseChatModel] = None,
        agent_names: Optional[List[str]] = None,
    ) -> Dict[str, CompiledGraph]:
        """
        批量创建所有配置的 Agent。

        Args:
            llm: 使用的 LLM 模型
            agent_names: 要创建的 Agent 名称列表，默认创建所有

        Returns:
            Agent 名称到实例的映射
        """
        names = agent_names or list(AGENT_CONFIGS.keys())
        agents = {}
        for name in names:
            try:
                agents[name] = self.create_agent(name, llm=llm)
            except Exception as e:
                logger.error("agent_creation_failed", name=name, error=str(e))
        return agents

    def _resolve_tools(
        self,
        explicit_tools: Optional[List[Union[str, LCBaseTool]]],
        config_tools: List[str],
    ) -> List[LCBaseTool]:
        """
        解析工具列表。

        优先级：显式传入的工具 > 配置中的工具 > 默认工具

        使用 ToolRegistry 获取工具实例。
        """
        if explicit_tools is not None:
            # 使用显式传入的工具
            resolved = []
            for tool in explicit_tools:
                if isinstance(tool, str):
                    # 工具名称，从注册表查找
                    t = ToolRegistry.get(tool)
                    if t:
                        resolved.append(t)
                    else:
                        # 回退到 langchain_tools
                        t = get_tool(tool)
                        if t:
                            resolved.append(t)
                else:
                    resolved.append(tool)
            return resolved

        # 使用配置中的工具
        if config_tools:
            # 优先从注册表获取
            tools = ToolRegistry.get_all(config_tools)
            if tools:
                return tools
            # 回退到 langchain_tools
            return get_tools(config_tools)

        # 使用默认工具
        return self._default_tools

    def _build_default_prompt(self, config: AgentConfig) -> str:
        """构建默认系统提示"""
        prompt_parts = [
            f"你是{config.role}。",
            "",
            "请分析给定的信息，提供你的专业见解。",
            "",
            "输出格式要求：",
            "- 提供清晰的分析结论",
            "- 列出支持证据",
            "- 给出置信度评分（0.0-1.0）",
        ]

        if config.tools:
            prompt_parts.extend([
                "",
                "你可以使用以下工具：",
                ", ".join(config.tools),
            ])

        return "\n".join(prompt_parts)

    def _build_state_modifier(self, system_prompt: str, config: AgentConfig) -> str:
        """
        构建 state_modifier 字符串。

        state_modifier 用于自定义 Agent 的系统消息和行为。
        """
        return f"""{system_prompt}

重要约束：
- 输出不要超过 {config.max_tokens} tokens
- 如果需要更多信息，明确指出缺失的信息
- 给出你的置信度评分（0.0-1.0）
"""

    def _get_cache_key(
        self,
        name: str,
        llm: Optional[BaseChatModel],
        tools: Optional[List[Union[str, LCBaseTool]]],
        system_prompt: Optional[str],
    ) -> str:
        """生成缓存键"""
        tool_names = []
        if tools:
            for t in tools:
                if isinstance(t, str):
                    tool_names.append(t)
                else:
                    tool_names.append(getattr(t, "name", str(t)))

        llm_id = id(llm) if llm else "default"
        tools_str = ",".join(sorted(tool_names)) if tool_names else "default"
        prompt_hash = hash(system_prompt) if system_prompt else "default"

        return f"{name}:{llm_id}:{tools_str}:{prompt_hash}"

    def clear_cache(self) -> None:
        """清除 Agent 缓存"""
        self._agent_cache.clear()
        logger.info("agent_cache_cleared")


# ============================================================================
# Module-level Factory Instance
# ============================================================================

# 全局默认工厂实例
_default_factory: Optional[AgentFactory] = None


def get_default_factory() -> AgentFactory:
    """获取默认工厂实例"""
    global _default_factory
    if _default_factory is None:
        _default_factory = AgentFactory()
    return _default_factory


def set_default_factory(factory: AgentFactory) -> None:
    """设置默认工厂实例"""
    global _default_factory
    _default_factory = factory


__all__ = [
    "AgentFactory",
    "get_default_factory",
    "set_default_factory",
]