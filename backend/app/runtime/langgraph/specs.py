"""
Agent catalog for LangGraph runtime.

Agent 规格定义模块，提供 AgentSpec 的构建和序列管理。
以 langgraph 内建默认配置为主，可选读取 runtime.agents 配置进行覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from app.runtime.langgraph.state import AgentSpec


@dataclass(frozen=True)
class _SpecConfig:
    name: str
    role: str
    phase: str
    system_prompt: str
    tools: tuple[str, ...] = ()
    max_tokens: int = 320
    timeout: int = 35
    temperature: float = 0.15
    enabled: bool = True


_DEFAULT_SPECS: Dict[str, _SpecConfig] = {
    "LogAgent": _SpecConfig(
        name="LogAgent",
        role="日志分析专家",
        phase="analysis",
        system_prompt="你是日志分析专家，聚焦错误日志、堆栈、时间线与性能异常证据。",
        tools=("parse_log", "read_file", "search_in_files"),
        max_tokens=320,
        timeout=35,
    ),
    "DomainAgent": _SpecConfig(
        name="DomainAgent",
        role="领域映射专家",
        phase="analysis",
        system_prompt="你是领域映射专家，负责接口到领域/聚合根/责任田的映射与业务影响评估。",
        tools=("ddd_analyzer", "read_file"),
        max_tokens=320,
        timeout=35,
    ),
    "CodeAgent": _SpecConfig(
        name="CodeAgent",
        role="代码分析专家",
        phase="analysis",
        system_prompt="你是代码分析专家，定位代码路径、并发/资源瓶颈、异常传播与回归风险。",
        tools=("git_tool", "read_file", "search_in_files", "list_files"),
        max_tokens=420,
        timeout=40,
    ),
    "MetricsAgent": _SpecConfig(
        name="MetricsAgent",
        role="监控指标专家",
        phase="analysis",
        system_prompt="你是监控指标专家，聚焦 CPU/线程/连接池/错误率时序证据并识别异常窗口。",
        tools=("metrics_snapshot",),
        max_tokens=360,
        timeout=35,
    ),
    "ChangeAgent": _SpecConfig(
        name="ChangeAgent",
        role="变更关联专家",
        phase="analysis",
        system_prompt="你是变更关联专家，分析最近发布、提交与故障时间窗的相关性。",
        tools=("git_tool", "search_in_files"),
        max_tokens=360,
        timeout=40,
    ),
    "RunbookAgent": _SpecConfig(
        name="RunbookAgent",
        role="处置手册专家",
        phase="analysis",
        system_prompt="你是处置手册专家，从案例库检索相似故障并给出可执行 SOP。",
        tools=("case_library", "read_file"),
        max_tokens=360,
        timeout=35,
    ),
    "CriticAgent": _SpecConfig(
        name="CriticAgent",
        role="架构质疑专家",
        phase="critique",
        system_prompt="你是架构质疑专家，挑战当前结论中的假设、证据缺口与逻辑漏洞。",
        tools=("read_file", "search_in_files"),
        max_tokens=420,
        timeout=40,
    ),
    "RebuttalAgent": _SpecConfig(
        name="RebuttalAgent",
        role="技术反驳专家",
        phase="rebuttal",
        system_prompt="你是技术反驳专家，回应质疑并补充证据，必要时修正结论。",
        tools=("read_file", "search_in_files"),
        max_tokens=420,
        timeout=40,
    ),
    "JudgeAgent": _SpecConfig(
        name="JudgeAgent",
        role="技术委员会主席",
        phase="judgment",
        system_prompt="你是技术委员会主席，整合所有证据，给出最终根因、修复与风险建议。",
        tools=(),
        max_tokens=900,
        timeout=60,
    ),
    "VerificationAgent": _SpecConfig(
        name="VerificationAgent",
        role="验证计划专家",
        phase="verification",
        system_prompt="你是验证计划专家，基于裁决结论输出功能/性能/回归/回滚验证计划。",
        tools=(),
        max_tokens=420,
        timeout=35,
    ),
    "ProblemAnalysisAgent": _SpecConfig(
        name="ProblemAnalysisAgent",
        role="问题分析主Agent/调度协调者",
        phase="coordination",
        system_prompt=(
            "你是生产故障问题分析主Agent。你负责拆解问题、向各专家Agent下达命令，并收敛最终结论。"
            "请输出紧凑 JSON。"
        ),
        tools=("read_file", "search_in_files"),
        max_tokens=600,
        timeout=45,
    ),
}


def _to_spec(config: _SpecConfig) -> AgentSpec:
    return AgentSpec(
        name=config.name,
        role=config.role,
        phase=config.phase,
        system_prompt=config.system_prompt,
        tools=config.tools,
        max_tokens=config.max_tokens,
        timeout=config.timeout,
        temperature=config.temperature,
    )


def _optional_external_specs() -> Optional[Dict[str, AgentSpec]]:
    try:
        from app.runtime.agents.config import get_all_agent_configs
    except Exception:
        return None
    try:
        configs = get_all_agent_configs()
    except Exception:
        return None
    result: Dict[str, AgentSpec] = {}
    for name, cfg in (configs or {}).items():
        if not bool(getattr(cfg, "enabled", True)):
            continue
        result[name] = AgentSpec.from_config(cfg)
    return result or None


def _build_spec_map() -> Dict[str, AgentSpec]:
    defaults = {name: _to_spec(cfg) for name, cfg in _DEFAULT_SPECS.items() if cfg.enabled}
    external = _optional_external_specs()
    if external:
        defaults.update(external)
    return defaults


def problem_analysis_agent_spec() -> AgentSpec:
    """创建问题分析主 Agent 规格。"""
    return _build_spec_map().get("ProblemAnalysisAgent") or _to_spec(_DEFAULT_SPECS["ProblemAnalysisAgent"])


def agent_sequence(*, enable_critique: bool) -> List[AgentSpec]:
    """
    生成 Agent 执行序列。

    Args:
        enable_critique: 是否启用批判环节（CriticAgent 和 RebuttalAgent）

    Returns:
        AgentSpec 列表，按执行顺序排列
    """
    specs_by_name = _build_spec_map()
    specs: List[AgentSpec] = []

    # 分析阶段 - 按顺序添加 LogAgent, DomainAgent, CodeAgent
    analysis_order = ["LogAgent", "DomainAgent", "CodeAgent", "MetricsAgent", "ChangeAgent", "RunbookAgent"]
    for name in analysis_order:
        if name in specs_by_name:
            specs.append(specs_by_name[name])

    # 批判阶段
    if enable_critique:
        critique_order = ["CriticAgent", "RebuttalAgent"]
        for name in critique_order:
            if name in specs_by_name:
                specs.append(specs_by_name[name])

    # 裁决阶段
    if "JudgeAgent" in specs_by_name:
        specs.append(specs_by_name["JudgeAgent"])

    # 验证阶段
    if "VerificationAgent" in specs_by_name:
        specs.append(specs_by_name["VerificationAgent"])

    return specs
