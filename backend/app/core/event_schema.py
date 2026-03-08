"""
统一事件模型模块

本模块提供事件标准化和追踪功能，是运行时事件系统的核心组件。

核心功能：
1. 生成追踪 ID（trace_id）
2. 事件标准化（添加时间戳、版本等）
3. 事件去重（生成稳定的 event_id）
4. 事件标识（生成客户端去重键）

事件流设计：
Agent 执行 -> emit() -> enrich_event() -> 添加标准字段 -> WebSocket 推送

主要组件：
- new_trace_id(): 生成追踪 ID
- enrich_event(): 事件标准化
- build_event_dedupe_key(): 构建去重键
- _build_stable_event_id(): 构建稳定事件 ID

Unified Event Schema
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo


# 事件模型版本号
EVENT_SCHEMA_VERSION = "v1"

# 北京时区，用于统一时间显示
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def new_trace_id(prefix: str = "trc") -> str:
    """
    生成追踪 ID

    用于跨系统追踪请求链路，格式为：{prefix}_{uuid_12位}。

    Args:
        prefix: ID 前缀，默认为 "trc"

    Returns:
        str: 追踪 ID，如 "trc_abc123def456"

    Example:
        >>> new_trace_id()
        'trc_abc123def456'
        >>> new_trace_id("debate")
        'debate_abc123def456'
    """
    return f"{prefix}_{uuid4().hex[:12]}"


def _build_stable_event_id(payload: Dict[str, Any]) -> str:
    """
    构建稳定的事件 ID

    对于相同的 payload 对象，返回相同的 ID。
    这确保了 WebSocket 推送和持久化事件的一致性。

    稳定性策略：
    - 使用 session_id + event_sequence 作为主要种子
    - 排除时间戳，避免重放时 ID 变化

    Args:
        payload: 事件数据字典

    Returns:
        str: 稳定的事件 ID，格式为 "evt_{sha1_20位}"
    """
    # 使用确定性字段构建种子
    # 时间戳不参与 ID 生成，保证重放时 ID 稳定
    seed = {
        "type": payload.get("type"),
        "phase": payload.get("phase"),
        "session_id": payload.get("session_id"),
        "trace_id": payload.get("trace_id"),
        "agent_name": payload.get("agent_name"),
        "round_number": payload.get("round_number"),
        "loop_round": payload.get("loop_round"),
        "event_sequence": payload.get("event_sequence"),
        "stream_id": payload.get("stream_id"),
        "chunk_index": payload.get("chunk_index"),
        "chunk_total": payload.get("chunk_total"),
    }
    # 如果没有 event_sequence，则使用时间戳
    if not payload.get("event_sequence"):
        seed["timestamp"] = payload.get("timestamp")
    # 序列化并计算 SHA1 哈希
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
    return f"evt_{digest}"


def build_event_dedupe_key(payload: Dict[str, Any]) -> str:
    """
    构建客户端去重键

    用于前端渲染时识别重复事件，避免重复展示。

    去重键格式：
    - 有 session_id 和 event_sequence: "{session_id}:{event_sequence}:{event_type}"
    - 有流式数据: 追加 ":{stream_id}:{chunk_index}"
    - 无序号: "{event_type}:{phase}:{agent_name}:{stream_id}:{chunk_index}"

    Args:
        payload: 事件数据字典

    Returns:
        str: 去重键字符串
    """
    session_id = str(payload.get("session_id") or "").strip()
    event_sequence = str(payload.get("event_sequence") or "").strip()
    event_type = str(payload.get("type") or "").strip()
    stream_id = str(payload.get("stream_id") or "").strip()
    chunk_index = str(payload.get("chunk_index") or "").strip()
    phase = str(payload.get("phase") or "").strip()
    agent_name = str(payload.get("agent_name") or payload.get("agent") or "").strip()

    # 优先使用 session_id + event_sequence 构建稳定键
    if session_id and event_sequence:
        base = f"{session_id}:{event_sequence}:{event_type}"
        if stream_id:
            base = f"{base}:{stream_id}:{chunk_index or '-'}"
        return base

    # 回退到其他字段组合
    return f"{event_type}:{phase}:{agent_name}:{stream_id}:{chunk_index}"


def enrich_event(
    event: Dict[str, Any],
    trace_id: Optional[str] = None,
    default_phase: Optional[str] = None,
) -> Dict[str, Any]:
    """
    事件标准化（enrich）

    为事件添加标准字段，确保所有事件具有一致的结构。

    添加的标准字段：
    - timestamp: UTC 时间戳
    - timestamp_bj: 北京时间戳
    - payload_version: 事件模型版本
    - trace_id: 追踪 ID
    - event_id: 稳定的事件 ID
    - dedupe_key: 客户端去重键
    - phase: 执行阶段（可选默认值）
    - agent: Agent 名称（与 agent_name 同步）

    Args:
        event: 原始事件数据
        trace_id: 追踪 ID，未提供则自动生成
        default_phase: 默认执行阶段

    Returns:
        Dict[str, Any]: 标准化后的事件数据
    """
    payload = dict(event or {})

    # 添加时间戳
    payload.setdefault("timestamp", datetime.utcnow().isoformat())
    payload.setdefault("timestamp_bj", datetime.now(BEIJING_TZ).isoformat())

    # 添加版本号
    payload.setdefault("payload_version", EVENT_SCHEMA_VERSION)

    # 添加追踪 ID
    payload.setdefault("trace_id", trace_id or new_trace_id())

    # 添加稳定的事件 ID 和去重键
    payload.setdefault("event_id", _build_stable_event_id(payload))
    payload.setdefault("dedupe_key", build_event_dedupe_key(payload))

    # 设置默认执行阶段
    if default_phase and not payload.get("phase"):
        payload["phase"] = default_phase

    # 同步 agent_name 和 agent 字段
    if payload.get("agent_name") and not payload.get("agent"):
        payload["agent"] = payload["agent_name"]

    return payload