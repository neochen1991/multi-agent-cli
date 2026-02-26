"""Agent catalog for LangGraph runtime."""

from __future__ import annotations

from typing import List

from app.runtime.langgraph.state import AgentSpec


def problem_analysis_agent_spec() -> AgentSpec:
    return AgentSpec(
        name="ProblemAnalysisAgent",
        role="问题分析主Agent/调度协调者",
        phase="analysis",
        system_prompt=(
            "你是生产故障问题分析主Agent。你负责拆解问题、向各专家Agent下达命令，并收敛最终结论。"
            "请输出紧凑 JSON。"
        ),
    )


def agent_sequence(*, enable_critique: bool) -> List[AgentSpec]:
    sequence = [
        AgentSpec(
            name="LogAgent",
            role="日志分析专家",
            phase="analysis",
            system_prompt=(
                "你是生产故障日志分析专家。只输出紧凑 JSON。"
                "聚焦异常模式、调用链、资源指标与关键证据。"
            ),
        ),
        AgentSpec(
            name="DomainAgent",
            role="领域映射专家",
            phase="analysis",
            system_prompt=(
                "你是 DDD 领域映射专家。只输出紧凑 JSON。"
                "必须将接口现象映射到 domain/aggregate/responsibility。"
            ),
        ),
        AgentSpec(
            name="CodeAgent",
            role="代码分析专家",
            phase="analysis",
            system_prompt=(
                "你是代码根因分析专家。只输出紧凑 JSON。"
                "给出最可能代码位置、触发条件和修复建议。"
            ),
        ),
    ]
    if enable_critique:
        sequence.extend(
            [
                AgentSpec(
                    name="CriticAgent",
                    role="架构质疑专家",
                    phase="critique",
                    system_prompt=(
                        "你是技术评审质疑专家。只输出紧凑 JSON。"
                        "找出前面结论中的漏洞和不充分证据。"
                    ),
                ),
                AgentSpec(
                    name="RebuttalAgent",
                    role="技术反驳专家",
                    phase="rebuttal",
                    system_prompt=(
                        "你是技术反驳专家。只输出紧凑 JSON。"
                        "针对质疑补充证据，收敛到可执行结论。"
                    ),
                ),
            ]
        )
    sequence.append(
        AgentSpec(
            name="JudgeAgent",
            role="技术委员会主席",
            phase="judgment",
            system_prompt=(
                "你是技术委员会主席。基于证据给出最终裁决。"
                "必须只输出 JSON，字段严格包含 final_judgment 与 confidence。"
            ),
        )
    )
    return sequence
