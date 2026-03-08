"""
Agent 间消息邮箱模块

本模块提供 Agent 间显式通信的邮箱功能。

邮箱设计：
- 每个Agent 有一个收件箱（receiver -> messages）
- 消息类型包括：证据、问题、结论、命令、反馈
- 邮箱大小有限制，防止内存膨胀

主要功能：
- clone_mailbox: 克隆邮箱，用于状态更新
- enqueue_message: 向邮箱添加消息
- dequeue_messages: 从邮箱取出消息
- compact_mailbox: 压缩邮箱，控制大小

使用场景：
- Commander 向 Agent 发送命令
- Agent 向 Commander 发送反馈
- Agent 之间共享证据

Explicit inter-agent mailbox helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.runtime.messages import AgentMessage


def clone_mailbox(mailbox: Dict[str, List[Dict[str, Any]]] | None) -> Dict[str, List[Dict[str, Any]]]:
    """
    克隆邮箱

    创建邮箱的深拷贝，用于状态更新时避免引用问题。

    Args:
        mailbox: 原始邮箱

    Returns:
        Dict[str, List[Dict[str, Any]]]: 克隆后的邮箱
    """
    source = dict(mailbox or {})
    return {str(k): [dict(item) for item in list(v or [])] for k, v in source.items()}


def enqueue_message(
    mailbox: Dict[str, List[Dict[str, Any]]],
    *,
    receiver: str,
    message: AgentMessage,
    max_per_receiver: int = 20,
) -> None:
    """
    向邮箱添加消息

    将消息添加到指定接收者的收件箱。
    如果收件箱超过限制，保留最近的消息。

    Args:
        mailbox: 邮箱字典（会被修改）
        receiver: 接收者名称
        message: 消息对象
        max_per_receiver: 每个接收者最大消息数

    Note:
        此函数直接修改 mailbox 参数，不返回新字典
    """
    key = str(receiver or "").strip()
    if not key:
        return
    bucket = list(mailbox.get(key) or [])
    bucket.append(message.model_dump(mode="json"))
    # 限制消息数量，保留最近的
    if len(bucket) > max_per_receiver:
        bucket = bucket[-max_per_receiver:]
    mailbox[key] = bucket


def dequeue_messages(
    mailbox: Dict[str, List[Dict[str, Any]]],
    *,
    receiver: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    从邮箱取出消息

    取出指定接收者的所有消息，并从邮箱中移除。
    返回取出的消息和更新后的邮箱。

    Args:
        mailbox: 邮箱字典
        receiver: 接收者名称

    Returns:
        Tuple[List[Dict], Dict]: (取出的消息列表, 更新后的邮箱)
    """
    copied = clone_mailbox(mailbox)
    key = str(receiver or "").strip()
    items = list(copied.pop(key, []) or [])
    return items, copied


def compact_mailbox(mailbox: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    压缩邮箱

    清理邮箱中的无效数据，限制每个接收者的消息数量。
    用于控制状态体积，防止内存膨胀。

    Args:
        mailbox: 原始邮箱

    Returns:
        Dict[str, List[Dict[str, Any]]]: 压缩后的邮箱
    """
    compacted: Dict[str, List[Dict[str, Any]]] = {}
    for receiver, messages in (mailbox or {}).items():
        # 过滤无效消息
        arr = [dict(item) for item in list(messages or []) if isinstance(item, dict)]
        if arr:
            # 每个接收者最多保留 20 条消息
            compacted[str(receiver)] = arr[-20:]
    return compacted


__all__ = [
    "clone_mailbox",
    "enqueue_message",
    "dequeue_messages",
    "compact_mailbox",
]

