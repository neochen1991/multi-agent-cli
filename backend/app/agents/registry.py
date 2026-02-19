"""
Agent 注册中心
Agent Registry

管理和注册所有可用的 Agent 实例。
"""

from typing import Any, Dict, List, Optional, Type
import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger()


class AgentRegistry:
    """
    Agent 注册中心
    
    单例模式，管理所有 Agent 的注册和获取。
    """
    
    _instance: Optional["AgentRegistry"] = None
    _agents: Dict[str, BaseAgent] = {}
    _agent_classes: Dict[str, Type[BaseAgent]] = {}
    
    def __new__(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, name: str, agent_class: Type[BaseAgent]) -> None:
        """
        注册 Agent 类
        
        Args:
            name: Agent 名称
            agent_class: Agent 类
        """
        cls._agent_classes[name] = agent_class
        logger.info("agent_class_registered", name=name)
    
    @classmethod
    async def get_agent(cls, name: str, **kwargs) -> BaseAgent:
        """
        获取 Agent 实例
        
        Args:
            name: Agent 名称
            **kwargs: Agent 初始化参数
            
        Returns:
            Agent 实例
        """
        if name in cls._agents:
            return cls._agents[name]
        
        if name not in cls._agent_classes:
            raise ValueError(f"Agent '{name}' not registered")
        
        agent_class = cls._agent_classes[name]
        agent = agent_class(**kwargs)
        cls._agents[name] = agent
        
        logger.info("agent_instance_created", name=name)
        return agent
    
    @classmethod
    def list_agents(cls) -> List[str]:
        """
        列出所有已注册的 Agent
        
        Returns:
            Agent 名称列表
        """
        return list(cls._agent_classes.keys())
    
    @classmethod
    def get_agent_info(cls, name: str) -> Dict[str, Any]:
        """
        获取 Agent 信息
        
        Args:
            name: Agent 名称
            
        Returns:
            Agent 信息字典
        """
        if name not in cls._agent_classes:
            return {}
        
        agent_class = cls._agent_classes[name]
        
        # 创建临时实例获取信息
        temp_instance = agent_class.__new__(agent_class)
        info = {
            "name": name,
            "class": agent_class.__name__,
            "role": getattr(temp_instance, "role", "unknown"),
            "model": getattr(temp_instance, "model", "unknown"),
        }
        
        return info
    
    @classmethod
    def clear(cls) -> None:
        """清空所有注册"""
        cls._agents.clear()
        cls._agent_classes.clear()
        logger.info("agent_registry_cleared")


def register_agent(name: str):
    """
    Agent 注册装饰器
    
    使用方式：
        @register_agent("log_agent")
        class LogAgent(BaseAgent):
            ...
    
    Args:
        name: Agent 名称
    """
    def decorator(cls: Type[BaseAgent]) -> Type[BaseAgent]:
        AgentRegistry.register(name, cls)
        return cls
    return decorator
