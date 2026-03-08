"""
上下文服务模块

本模块提供 LangGraph 辩论运行时的上下文构建和管理功能。

核心功能：
1. 上下文压缩
2. 同伴项收集
3. 对话项提取
4. 会话状态派生
5. Agent 提示词上下文构建

上下文结构：
- incident_summary: 故障摘要
- error_type: 错误类型
- key_entities: 关键实体
- time_range: 时间范围
- affected_services: 受影响服务

使用场景：
- 为 Agent 构建执行上下文
- 压缩长文本以适应 Token 限制
- 收集其他 Agent 的输出作为上下文

Context service for LangGraph debate runtime.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from app.runtime.messages import AgentEvidence

logger = structlog.get_logger()


class ContextService:
    """
    上下文构建和管理服务

    提供上下文的构建、压缩和管理功能。

    属性：
    - _context_cache: 上下文缓存

    功能：
    - 压缩上下文：提取关键字段
    - 收集同伴项：获取其他 Agent 的输出
    - 提取对话项：从消息中提取对话历史
    - 派生会话状态：从历史中推导当前状态
    """

    def __init__(self) -> None:
        """
        初始化上下文服务

        创建空的上下文缓存。
        """
        self._context_cache: Dict[str, Dict[str, Any]] = {}

    def compact_round_context(
        self,
        context_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        压缩回合上下文

        提取关键信息，减少 Token 消耗。

        Args:
            context_summary: 原始上下文摘要

        Returns:
            Dict[str, Any]: 压缩后的上下文
        """
        if not context_summary:
            return {}

        # 提取关键字段
        compact = {
            "incident_summary": context_summary.get("incident_summary", ""),
            "error_type": context_summary.get("error_type", ""),
            "key_entities": list(context_summary.get("key_entities", []))[:5],
            "time_range": context_summary.get("time_range", {}),
            "affected_services": list(context_summary.get("affected_services", []))[:3],
        }

        # 移除空值
        return {k: v for k, v in compact.items() if v}

    def collect_peer_items_from_cards(
        self,
        history_cards: List[AgentEvidence],
        agent_names: List[str],
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        从历史卡片收集同伴项

        获取指定 Agent 的最新输出作为上下文。

        Args:
            history_cards: 历史卡片列表
            agent_names: 要收集的 Agent 名称列表
            limit: 每个 Agent 的最大项数

        Returns:
            List[Dict[str, Any]]: 同伴项列表
        """
        peer_items = []
        seen_agents = set()

        # 从最新的卡片开始遍历
        for card in reversed(history_cards):
            if card.agent_name in agent_names and card.agent_name not in seen_agents:
                peer_items.append({
                    "agent_name": card.agent_name,
                    "conclusion": str(card.conclusion or "")[:500],
                    "confidence": float(card.confidence or 0.0),
                    "evidence_chain": list(card.evidence_chain or [])[:limit],
                })
                seen_agents.add(card.agent_name)

                if len(seen_agents) >= len(agent_names):
                    break

        return peer_items

    def dialogue_items_from_messages(
        self,
        messages: List[Any],
        limit: int = 6,
        char_budget: int = 720,
    ) -> List[Dict[str, Any]]:
        """
        从消息中提取对话项

        提取最近的对话历史，控制字符数。

        Args:
            messages: 消息列表
            limit: 最大项数
            char_budget: 字符预算

        Returns:
            List[Dict[str, Any]]: 对话项列表
        """
        items = []
        total_chars = 0

        for msg in reversed(messages):
            if len(items) >= limit:
                break

            # 提取内容
            content = ""
            if hasattr(msg, "content"):
                content = str(msg.content or "")
            elif isinstance(msg, dict):
                content = str(msg.get("content", ""))

            if not content.strip():
                continue

            # 提取发送者
            sender = "unknown"
            if hasattr(msg, "name") and msg.name:
                sender = str(msg.name)
            elif isinstance(msg, dict):
                sender = str(msg.get("name", "unknown"))

            # 截断到预算
            if total_chars + len(content) > char_budget:
                remaining = char_budget - total_chars
                if remaining > 50:
                    content = content[:remaining] + "..."
                else:
                    break

            items.append({
                "sender": sender,
                "content": content,
            })
            total_chars += len(content)

        return list(reversed(items))

    def derive_conversation_state(
        self,
        history_cards: List[AgentEvidence],
        messages: List[Any],
        existing_agent_outputs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        从历史派生会话状态

        提取开放问题、声明和统计信息。

        Args:
            history_cards: 历史卡片列表
            messages: 消息列表
            existing_agent_outputs: 现有 Agent 输出

        Returns:
            Dict[str, Any]: 派生的会话状态
        """
        # 收集开放问题
        open_questions = []
        for output in existing_agent_outputs.values():
            if isinstance(output, dict):
                for key in ("open_questions", "missing_info", "needs_validation"):
                    value = output.get(key)
                    if isinstance(value, list):
                        open_questions.extend([
                            str(v or "").strip() for v in value
                            if str(v or "").strip()
                        ])
                    elif isinstance(value, str) and value.strip():
                        open_questions.append(value.strip())

        # 去重并保持顺序
        seen = set()
        unique_questions = []
        for q in open_questions:
            if q not in seen:
                seen.add(q)
                unique_questions.append(q)

        # 收集声明
        claims = []
        for card in history_cards:
            if card.conclusion:
                claims.append({
                    "agent_name": card.agent_name,
                    "claim": str(card.conclusion)[:200],
                    "confidence": float(card.confidence or 0.0),
                })

        return {
            "open_questions": unique_questions[:10],
            "claims": claims[-10:],
            "total_turns": len(history_cards),
            "unique_agents": len(set(c.agent_name for c in history_cards if c.agent_name)),
        }

    def build_agent_prompt_context(
        self,
        spec: Any,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        构建 Agent 提示词上下文

        为 Agent 构建完整的执行上下文。

        Args:
            spec: Agent 规格
            loop_round: 当前循环轮次
            context: 压缩上下文
            history_cards: 历史卡片
            assigned_command: 分配给 Agent 的命令
            dialogue_items: 对话项
            inbox_messages: 收件箱消息

        Returns:
            Dict[str, Any]: 提示词上下文字典
        """
        return {
            "agent_name": spec.name,
            "agent_role": spec.role,
            "loop_round": loop_round,
            "context": context,
            "recent_history": [
                {
                    "agent_name": c.agent_name,
                    "conclusion": str(c.conclusion or "")[:300],
                    "confidence": float(c.confidence or 0.0),
                }
                for c in history_cards[-5:]
            ],
            "assigned_command": assigned_command,
            "dialogue_items": dialogue_items or [],
            "inbox_messages": inbox_messages or [],
        }

    def clear_cache(self) -> None:
        """
        清空上下文缓存
        """
        self._context_cache.clear()


__all__ = ["ContextService"]