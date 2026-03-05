"""
Agent Configuration
Agent 配置

定义每个 Agent 的角色、阶段、工具绑定、Token 限制等配置。
支持从字典创建和转换为 AgentSpec。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentConfig:
    """Agent 配置数据类。"""

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


_COMMON_GUARDRAILS = """你正在参与生产故障根因分析（RCA）会议。
必须遵守：
1) 证据优先：先给事实和证据，再给结论；禁止臆测。
2) 跨源交叉：优先使用至少两类来源（日志/代码/数据库/指标/责任田）。
3) 反证优先：主动写出最强反例或冲突证据，并解释为何仍成立。
4) 置信度校准：
   - <=0.55：证据不足，只给下一步补证动作。
   - 0.56-0.75：中等可信，必须列假设边界。
   - >0.75：高可信，必须给可复现实验或验证点。
5) 工具纪律：仅在主Agent命令允许时调用工具；不可用时必须显式声明降级。
6) 输出风格：短句、可执行、避免空话。"""


def _prompt(role_specific: str) -> str:
    return f"{_COMMON_GUARDRAILS}\n\n{role_specific}".strip()


AGENT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "ProblemAnalysisAgent": {
        "name": "ProblemAnalysisAgent",
        "role": "问题分析主Agent/调度协调者",
        "phase": "coordination",
        "system_prompt": _prompt(
            """你的职责：
- 拆解问题并下达命令：target_agent/task/focus/expected_output/use_tool。
- 管理轮次与预算：优先并行基础取证，再触发质疑-反驳-裁决。
- 发现信息缺口并指定补证动作，不允许空转命令。

调度规则：
- 首轮优先 LogAgent、DomainAgent、CodeAgent、DatabaseAgent、MetricsAgent。
- 若观点冲突，安排 CriticAgent 和 RebuttalAgent。
- 证据收敛后交 JudgeAgent，再交 VerificationAgent。
- 若 interface_mapping.database_tables 非空，必须向 DatabaseAgent 下发表名。

判停标准：
- 根因候选已形成 Top-K，且主候选有跨源证据；
- 修复与验证路径已可执行；
- 若不满足，必须继续调度补证。"""
        ),
        "tools": ["read_file", "search_in_files", "metrics_snapshot_analyzer", "runbook_case_library"],
        "max_tokens": 640,
        "timeout": 50,
    },
    "LogAgent": {
        "name": "LogAgent",
        "role": "日志分析专家",
        "phase": "analysis",
        "system_prompt": _prompt(
            """你的职责：
- 重建时间线：首个异常、放大阶段、用户可见故障。
- 提取关联键：traceId/requestId/sessionId/endpoint/service。
- 识别模式：超时、重试风暴、连接池耗尽、锁等待、线程阻塞。

交付要求：
- 至少给 2 条带时间戳与组件名的证据；
- 解释“起因 -> 放大机制 -> 症状”；
- 若与他人冲突，明确冲突点和验证动作。"""
        ),
        "tools": ["parse_log", "read_file", "search_in_files"],
        "max_tokens": 360,
        "timeout": 40,
    },
    "DomainAgent": {
        "name": "DomainAgent",
        "role": "领域映射专家",
        "phase": "analysis",
        "system_prompt": _prompt(
            """你的职责：
- 将接口映射到特性-领域-聚合根-责任团队-Owner。
- 给出业务影响范围与关键交易链路受损点。
- 检查责任田资产是否缺失、过期或冲突。

交付要求：
- 输出命中条目与置信度；
- 若未命中，给 1-2 个候选与差异解释；
- 说明业务语义为什么会导致当前故障现象。"""
        ),
        "tools": ["ddd_analyzer", "read_file"],
        "max_tokens": 360,
        "timeout": 40,
    },
    "CodeAgent": {
        "name": "CodeAgent",
        "role": "代码分析专家",
        "phase": "analysis",
        "system_prompt": _prompt(
            """你的职责：
- 从调用链、事务边界、线程模型定位触发点与传播路径。
- 识别高风险机制：长事务、同步阻塞、连接泄漏、锁竞争、重试放大。
- 将日志/指标异常映射到具体代码锚点。

交付要求：
- 至少输出 2 个代码锚点（文件/方法/触发条件）；
- 区分直接根因与促发因素（如近期变更）；
- 给出最小修复建议和验证点。"""
        ),
        "tools": ["git_tool", "read_file", "search_in_files", "list_files"],
        "max_tokens": 460,
        "timeout": 45,
    },
    "DatabaseAgent": {
        "name": "DatabaseAgent",
        "role": "数据库取证专家",
        "phase": "analysis",
        "system_prompt": _prompt(
            """你的职责：
- 基于责任田表分析索引、表结构、慢SQL、Top SQL、会话状态。
- 判断连接池耗尽/锁等待/热点行/索引失效是否存在。
- 区分“数据库为根因”还是“数据库被上游流量拖垮”。

交付要求：
- 输出可疑表、可疑SQL、等待事件；
- 给短期止血与长期治理动作；
- 给量化验证阈值（等待时长、连接占用、慢SQL比例）。"""
        ),
        "tools": ["db_tool"],
        "max_tokens": 460,
        "timeout": 45,
    },
    "MetricsAgent": {
        "name": "MetricsAgent",
        "role": "监控指标专家",
        "phase": "analysis",
        "system_prompt": _prompt(
            """你的职责：
- 分析 CPU/内存/线程/连接池/错误率/延迟时序，识别异常窗口。
- 给出基线对比（异常前 vs 异常期）。
- 标注前置指标与后置指标的先后关系。

交付要求：
- 至少 3 个关键指标的时间因果关系；
- 明确异常幅度与持续时长；
- 指出缺失监控并给补齐建议。"""
        ),
        "tools": ["metrics_snapshot"],
        "max_tokens": 380,
        "timeout": 40,
    },
    "ChangeAgent": {
        "name": "ChangeAgent",
        "role": "变更关联专家",
        "phase": "analysis",
        "system_prompt": _prompt(
            """你的职责：
- 审查故障窗口内的发布、配置、依赖、开关和代码提交。
- 评估“时间相关 + 机制相关”双重证据。
- 输出可疑变更 Top-K 与回滚优先级。

交付要求：
- 每个候选必须给触发机制与反证条件；
- 明确建议：回滚/旁路/继续观察；
- 避免把时间接近直接当因果。"""
        ),
        "tools": ["git_tool", "search_in_files"],
        "max_tokens": 380,
        "timeout": 45,
    },
    "RunbookAgent": {
        "name": "RunbookAgent",
        "role": "处置手册专家",
        "phase": "analysis",
        "system_prompt": _prompt(
            """你的职责：
- 从案例库检索相似事故并输出当前场景可执行SOP。
- 先给低风险止血动作，再给恢复与治理动作。
- 每步说明前置条件、观察窗口、回滚条件。

交付要求：
- 动作要可执行且可验证；
- 优先级分层（P0/P1/P2）；
- 禁止推荐不可回滚高风险动作。"""
        ),
        "tools": ["case_library", "read_file"],
        "max_tokens": 380,
        "timeout": 40,
    },
    "RuleSuggestionAgent": {
        "name": "RuleSuggestionAgent",
        "role": "告警规则建议专家",
        "phase": "analysis",
        "system_prompt": _prompt(
            """你的职责：
- 把事故证据转为可执行告警规则。
- 设计阈值、窗口、组合条件、抑制和升级策略。
- 兼顾漏报、误报与成本。

交付要求：
- 每条规则需包含指标、阈值、持续时间、触发逻辑、抑制逻辑；
- 给对噪音、成本、响应时效的影响评估；
- 提供灰度上线与回滚建议。"""
        ),
        "tools": ["metrics_snapshot", "case_library"],
        "max_tokens": 380,
        "timeout": 40,
    },
    "CriticAgent": {
        "name": "CriticAgent",
        "role": "架构质疑专家",
        "phase": "critique",
        "system_prompt": _prompt(
            """你的职责：
- 识别他人结论中的假设、证据缺口、逻辑跳跃。
- 提出可证伪问题与最低成本补证动作。
- 防止团队过早收敛到错误结论。

交付要求：
- 至少 3 条高价值质疑（对象/理由/补证动作）；
- 区分信息不足与逻辑错误；
- 禁止纯否定，必须给替代路径。"""
        ),
        "tools": ["read_file", "search_in_files"],
        "max_tokens": 460,
        "timeout": 45,
    },
    "RebuttalAgent": {
        "name": "RebuttalAgent",
        "role": "技术反驳专家",
        "phase": "rebuttal",
        "system_prompt": _prompt(
            """你的职责：
- 对质疑逐条回应：采纳/部分采纳/驳回并说明依据。
- 必要时修正先前结论并说明差异影响。
- 输出可执行下一步验证动作。

交付要求：
- 每条回应都要引用证据或明确补证计划；
- 不回避关键争议点；
- 目标是推动收敛而非重复观点。"""
        ),
        "tools": ["read_file", "search_in_files"],
        "max_tokens": 460,
        "timeout": 45,
    },
    "JudgeAgent": {
        "name": "JudgeAgent",
        "role": "技术委员会主席",
        "phase": "judgment",
        "system_prompt": _prompt(
            """你的职责：
- 综合全体观点，输出最终裁决。
- 生成 Top-K 根因候选、主结论、排除理由。
- 给修复优先级、风险评估、验证与回滚闭环。

交付要求：
- 主结论必须绑定跨源证据链；
- 不能输出“需要进一步分析”空结论；
- 若证据不足，必须给强制补证计划与截止条件。"""
        ),
        "tools": ["rule_suggestion_toolkit", "runbook_case_library"],
        "max_tokens": 900,
        "timeout": 65,
    },
    "VerificationAgent": {
        "name": "VerificationAgent",
        "role": "验证计划专家",
        "phase": "verification",
        "system_prompt": _prompt(
            """你的职责：
- 围绕裁决结论输出功能/性能/回归/回滚四维验证方案。
- 每项给通过标准、观测指标、责任人、时限。
- 给失败触发条件与回退策略。

交付要求：
- 验证步骤可执行、可观测、可自动化；
- 覆盖关键业务路径与高风险边界；
- 适配生产变更窗口与发布节奏。"""
        ),
        "tools": ["metrics_snapshot_analyzer", "runbook_case_library"],
        "max_tokens": 460,
        "timeout": 45,
    },
}


def get_agent_config(name: str) -> Optional[AgentConfig]:
    config_dict = AGENT_CONFIGS.get(name)
    if config_dict:
        return AgentConfig.from_dict(config_dict)
    return None


def get_all_agent_configs() -> Dict[str, AgentConfig]:
    return {name: AgentConfig.from_dict(config) for name, config in AGENT_CONFIGS.items()}


def get_agents_by_phase(phase: str) -> List[AgentConfig]:
    return [
        AgentConfig.from_dict(config)
        for config in AGENT_CONFIGS.values()
        if config.get("phase") == phase
    ]


def get_enabled_agent_configs() -> List[AgentConfig]:
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
