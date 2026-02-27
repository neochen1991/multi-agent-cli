"""
Agent Configuration
Agent 配置

定义每个 Agent 的角色、阶段、工具绑定、Token 限制等配置。
支持 YAML/JSON 格式加载（可扩展）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentConfig:
    """
    Agent 配置数据类

    用于定义每个 Agent 的角色、阶段、工具绑定、Token 限制等配置。
    支持从字典创建和转换为 AgentSpec。

    职责说明：
    - name: Agent 唯一标识符
    - role: Agent 角色描述
    - phase: Agent 所属阶段（analysis, critique, rebuttal, judgment, coordination）
    - system_prompt: Agent 的系统提示
    - tools: Agent 可用的工具名称列表
    - max_tokens: 最大输出 token 数
    - timeout: 执行超时时间（秒）
    - temperature: LLM 温度参数
    - enabled: 是否启用该 Agent
    - extra: 额外的配置信息
    """

    name: str
    role: str
    phase: str
    system_prompt: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    max_tokens: int = 320
    timeout: int = 35
    temperature: float = 0.15
    enabled: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "role": self.role,
            "phase": self.phase,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "temperature": self.temperature,
            "enabled": self.enabled,
            "extra": self.extra,
        }

    def to_spec(self) -> "AgentSpec":
        """
        转换为 AgentSpec 实例。

        Returns:
            AgentSpec 实例，用于运行时 Agent 执行
        """
        from app.runtime.langgraph.state import AgentSpec
        return AgentSpec(
            name=self.name,
            role=self.role,
            phase=self.phase,
            system_prompt=self.system_prompt or "",
            tools=tuple(self.tools),
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            temperature=self.temperature,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """从字典创建"""
        return cls(
            name=data.get("name", "UnknownAgent"),
            role=data.get("role", ""),
            phase=data.get("phase", "analysis"),
            system_prompt=data.get("system_prompt"),
            tools=data.get("tools", []),
            max_tokens=data.get("max_tokens", 320),
            timeout=data.get("timeout", 35),
            temperature=data.get("temperature", 0.15),
            enabled=data.get("enabled", True),
            extra=data.get("extra", {}),
        )


# ============================================================================
# Agent Configurations
# ============================================================================

AGENT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "LogAgent": {
        "name": "LogAgent",
        "role": "日志分析专家",
        "phase": "analysis",
        "system_prompt": """你是日志分析专家，专注于分析应用日志以发现问题的根本原因。

你的职责：
1. 解析日志中的异常堆栈、错误消息
2. 识别关键错误模式和时间线
3. 提取相关的 Trace ID、请求 ID 等关联信息
4. 分析日志中的性能指标和异常趋势

输出格式要求：
- 提供清晰的分析结论
- 列出关键证据（日志片段、时间戳）
- 给出置信度评分（0.0-1.0）
- 指出可能的问题方向""",
        "tools": ["parse_log", "read_file", "search_in_files"],
        "max_tokens": 320,
        "timeout": 35,
    },
    "CodeAgent": {
        "name": "CodeAgent",
        "role": "代码分析专家",
        "phase": "analysis",
        "system_prompt": """你是代码分析专家，专注于分析源代码以识别潜在问题和错误根源。

你的职责：
1. 分析代码逻辑和潜在的 bug
2. 识别代码中的异常处理和边界条件
3. 追踪代码调用链和数据流
4. 分析 Git 提交历史中的相关变更

输出格式要求：
- 提供代码级别的分析结论
- 指出具体的代码位置（文件:行号）
- 分析代码可能的问题原因
- 给出置信度评分（0.0-1.0）""",
        "tools": ["git_tool", "read_file", "search_in_files", "list_files"],
        "max_tokens": 420,
        "timeout": 40,
    },
    "DomainAgent": {
        "name": "DomainAgent",
        "role": "领域映射专家",
        "phase": "analysis",
        "system_prompt": """你是领域映射专家，专注于将技术问题映射到业务领域上下文。

你的职责：
1. 分析问题涉及的领域边界和上下文
2. 识别问题对业务功能的影响范围
3. 追踪领域事件的传播路径
4. 分析领域模型与代码实现的对应关系

输出格式要求：
- 提供领域级别的分析视角
- 说明问题的业务影响
- 识别相关的领域概念和术语
- 给出置信度评分（0.0-1.0）""",
        "tools": ["ddd_analyzer", "read_file"],
        "max_tokens": 320,
        "timeout": 35,
    },
    "CriticAgent": {
        "name": "CriticAgent",
        "role": "架构质疑专家",
        "phase": "critique",
        "system_prompt": """你是架构质疑专家，负责挑战其他 Agent 的分析结论。

你的职责：
1. 审视其他 Agent 的分析逻辑
2. 发现可能的遗漏和假设
3. 提出替代解释和反驳观点
4. 识别分析中的不确定因素

输出格式要求：
- 明确指出质疑的观点
- 提供支持质疑的证据
- 说明质疑的严重程度
- 给出置信度评分（0.0-1.0）""",
        "tools": ["read_file", "search_in_files"],
        "max_tokens": 420,
        "timeout": 40,
    },
    "RebuttalAgent": {
        "name": "RebuttalAgent",
        "role": "技术反驳专家",
        "phase": "rebuttal",
        "system_prompt": """你是技术反驳专家，负责回应质疑并捍卫或修正分析结论。

你的职责：
1. 回应 CriticAgent 的质疑
2. 提供更多证据支持结论
3. 在必要时修正原有分析
4. 识别双方观点的共识和分歧

输出格式要求：
- 逐条回应质疑观点
- 提供补充证据
- 说明是否接受质疑并修正结论
- 给出置信度评分（0.0-1.0）""",
        "tools": ["read_file", "search_in_files"],
        "max_tokens": 420,
        "timeout": 40,
    },
    "JudgeAgent": {
        "name": "JudgeAgent",
        "role": "技术委员会主席",
        "phase": "judgment",
        "system_prompt": """你是技术委员会主席，负责综合所有证据给出最终裁决。

你的职责：
1. 综合所有 Agent 的分析结论
2. 权衡各方观点的可信度
3. 给出最终的根因判断
4. 提供修复建议和预防措施

输出格式要求：
- 提供明确的根因结论
- 列出支持结论的关键证据
- 给出修复建议和优先级
- 给出整体置信度评分（0.0-1.0）""",
        "tools": [],  # Judge 不需要使用工具，只需综合分析
        "max_tokens": 900,
        "timeout": 60,
    },
    "ProblemAnalysisAgent": {
        "name": "ProblemAnalysisAgent",
        "role": "问题分析协调者",
        "phase": "coordination",
        "system_prompt": """你是问题分析协调者，负责协调整个分析流程并决定下一步行动。

你的职责：
1. 分析当前收集的证据
2. 识别信息缺口
3. 决定下一步应该咨询哪个专家
4. 判断是否已有足够证据做出结论

输出格式要求：
- 提供当前分析状态总结
- 明确指定下一步行动（next_mode, next_agent）
- 给出是否应该停止的判断
- 说明决策理由""",
        "tools": ["read_file", "search_in_files"],
        "max_tokens": 600,
        "timeout": 45,
    },
}


def get_agent_config(name: str) -> Optional[AgentConfig]:
    """
    获取指定 Agent 的配置。

    Args:
        name: Agent 名称

    Returns:
        AgentConfig 实例，如果不存在返回 None
    """
    config_dict = AGENT_CONFIGS.get(name)
    if config_dict:
        return AgentConfig.from_dict(config_dict)
    return None


def get_all_agent_configs() -> Dict[str, AgentConfig]:
    """
    获取所有 Agent 的配置。

    Returns:
        Agent 名称到配置的映射
    """
    return {name: AgentConfig.from_dict(config) for name, config in AGENT_CONFIGS.items()}


def get_agents_by_phase(phase: str) -> List[AgentConfig]:
    """
    获取指定阶段的所有 Agent 配置。

    Args:
        phase: 阶段名称（analysis, critique, rebuttal, judgment）

    Returns:
        该阶段的 Agent 配置列表
    """
    return [
        AgentConfig.from_dict(config)
        for config in AGENT_CONFIGS.values()
        if config.get("phase") == phase
    ]


def get_enabled_agent_configs() -> List[AgentConfig]:
    """
    获取所有启用的 Agent 配置。

    Returns:
        启用的 Agent 配置列表
    """
    return [
        AgentConfig.from_dict(config)
        for config in AGENT_CONFIGS.values()
        if config.get("enabled", True)
    ]


__all__ = [
    "AgentConfig",
    "AGENT_CONFIGS",
    "get_agent_config",
    "get_all_agent_configs",
    "get_agents_by_phase",
    "get_enabled_agent_configs",
]