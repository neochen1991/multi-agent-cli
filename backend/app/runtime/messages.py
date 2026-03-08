"""
运行时消息契约模块

本模块定义 LangGraph 运行时的消息数据结构。

核心消息类型：
- AgentEvidence: Agent 输出证据卡片
- AgentMessage: Agent 间通信消息
- RoundCheckpoint: 回合检查点
- FinalVerdict: 最终裁决结果
- RuntimeState: 运行时完整状态

数据流：
Agent 执行 -> AgentEvidence -> history_cards -> 前端展示
Commander -> AgentMessage -> agent_mailbox -> Agent 接收
JudgeAgent -> FinalVerdict -> DebateResult

LangGraph runtime message contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AgentEvidence(BaseModel):
    """
    Agent 输出证据卡片

    标准化的 Agent 输出格式，包含：
    - agent_name: Agent 名称
    - phase: 执行阶段
    - summary: 输出摘要
    - conclusion: 结论
    - evidence_chain: 证据链
    - confidence: 置信度（0-1）
    - raw_output: 原始输出字典

    该模型是 Agent 输出的核心数据结构，
    用于 history_cards 和前端展示。
    """

    agent_name: str  # Agent 名称
    phase: str  # 执行阶段
    summary: str = ""  # 输出摘要
    conclusion: str = ""  # 结论
    evidence_chain: List[str] = Field(default_factory=list)  # 证据链
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # 置信度
    raw_output: Dict[str, Any] = Field(default_factory=dict)  # 原始输出


class AgentMessage(BaseModel):
    """
    Agent 间通信消息

    用于 Agent 之间的显式通信，支持：
    - evidence: 证据分享
    - question: 问题询问
    - conclusion: 结论通知
    - command: 命令下发
    - feedback: 反馈回复

    消息通过 agent_mailbox 传递：
    - sender: 发送者
    - receiver: 接收者（默认 broadcast）
    - message_type: 消息类型
    - content: 消息内容
    """

    sender: str  # 发送者
    receiver: str = Field(default="broadcast")  # 接收者
    message_type: Literal["evidence", "question", "conclusion", "command", "feedback"] = Field(
        default="evidence"
    )
    content: Dict[str, Any] = Field(default_factory=dict)  # 消息内容


class RoundCheckpoint(BaseModel):
    """
    回合检查点

    持久化的回合级别数据，用于：
    - 断点恢复
    - 状态追踪
    - 历史查询

    包含回合的基本信息和执行结果。
    """

    session_id: str  # 会话 ID
    round_number: int  # 回合编号
    loop_round: int  # 循环轮次
    phase: str  # 执行阶段
    agent_name: str  # Agent 名称
    confidence: float  # 置信度
    summary: str  # 摘要
    conclusion: str  # 结论
    created_at: datetime = Field(default_factory=datetime.utcnow)  # 创建时间


class FinalVerdict(BaseModel):
    """
    最终裁决结果

    由 JudgeAgent 产出的标准化裁决结果，包含：
    - root_cause: 根因分析
    - evidence_chain: 证据链
    - fix_recommendation: 修复建议
    - impact_analysis: 影响分析
    - risk_assessment: 风险评估

    该结果会被转换为 DebateResult 返回给调用者。
    """

    root_cause: Dict[str, Any] = Field(default_factory=dict)  # 根因分析
    evidence_chain: List[Dict[str, Any]] = Field(default_factory=list)  # 证据链
    fix_recommendation: Dict[str, Any] = Field(default_factory=dict)  # 修复建议
    impact_analysis: Dict[str, Any] = Field(default_factory=dict)  # 影响分析
    risk_assessment: Dict[str, Any] = Field(default_factory=dict)  # 风险评估


class RuntimeState(BaseModel):
    """
    运行时完整状态

    持久化到磁盘的完整运行时状态，用于：
    - 断点恢复
    - 调试分析
    - 状态同步

    包含会话的所有信息：
    - 会话标识
    - 状态信息
    - 上下文摘要
    - 回合历史
    - 最终裁决
    """

    session_id: str  # 会话 ID
    trace_id: str  # 追踪 ID
    status: str  # 状态
    started_at: datetime = Field(default_factory=datetime.utcnow)  # 开始时间
    updated_at: datetime = Field(default_factory=datetime.utcnow)  # 更新时间
    context_summary: Dict[str, Any] = Field(default_factory=dict)  # 上下文摘要
    rounds: List[RoundCheckpoint] = Field(default_factory=list)  # 回合列表
    final_verdict: Optional[FinalVerdict] = None  # 最终裁决
