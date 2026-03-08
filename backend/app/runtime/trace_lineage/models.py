"""
审计轨迹记录模型

本模块定义审计轨迹记录的类型和数据结构。

记录类型：
- session: 会话级别记录
- event: 事件记录
- agent: Agent 执行记录
- tool: 工具调用记录
- summary: 摘要记录

字段说明：
- session_id: 会话标识
- trace_id: 追踪标识
- seq: 序号（会话内递增）
- kind: 记录类型
- timestamp: 时间戳
- phase: 执行阶段
- agent_name: Agent 名称
- event_type: 事件类型
- confidence: 置信度
- duration_ms: 执行耗时
- input_summary: 输入摘要
- output_summary: 输出摘要
- tool_calls: 工具调用列表
- payload: 原始数据

Typed models for runtime lineage records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# 记录类型枚举
LineageRecordType = Literal["session", "event", "agent", "tool", "summary"]


class LineageRecord(BaseModel):
    """
    审计轨迹记录

    单条审计轨迹记录，以 JSONL 格式持久化。

    属性：
    - session_id: 会话 ID
    - trace_id: 追踪 ID
    - seq: 序号（会话内递增）
    - kind: 记录类型（session/event/agent/tool/summary）
    - timestamp: 时间戳
    - phase: 执行阶段
    - agent_name: Agent 名称
    - event_type: 事件类型
    - confidence: 置信度（0-1）
    - duration_ms: 执行耗时（毫秒）
    - input_summary: 输入摘要
    - output_summary: 输出摘要
    - tool_calls: 工具调用列表
    - payload: 原始数据字典
    """

    session_id: str  # 会话 ID
    trace_id: str = ""  # 追踪 ID
    seq: int = 0  # 序号
    kind: LineageRecordType  # 记录类型
    timestamp: datetime = Field(default_factory=datetime.utcnow)  # 时间戳
    phase: str = ""  # 执行阶段
    agent_name: str = ""  # Agent 名称
    event_type: str = ""  # 事件类型
    confidence: float = 0.0  # 置信度
    duration_ms: float = 0.0  # 执行耗时
    input_summary: Dict[str, Any] = Field(default_factory=dict)  # 输入摘要
    output_summary: Dict[str, Any] = Field(default_factory=dict)  # 输出摘要
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)  # 工具调用列表
    payload: Dict[str, Any] = Field(default_factory=dict)  # 原始数据