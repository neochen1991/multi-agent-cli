"""
Agent 模块
Multi-Agent System for SRE Debate Platform
"""

from app.agents.base import BaseAgent, AgentResult
from app.agents.registry import AgentRegistry

__all__ = [
    "BaseAgent",
    "AgentResult",
    "AgentRegistry",
]
