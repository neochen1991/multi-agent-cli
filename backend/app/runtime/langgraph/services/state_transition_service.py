"""
状态转换服务模块

本模块提供 LangGraph 运行时的状态转换功能。

核心功能：
1. 节点步骤结果合并
2. 状态投影（消息优先）
3. 结构化状态视图

设计原则：
- 消息优先投影：历史卡片是从回合卡片和消息投影而来
- 去重合并：新消息与现有消息去重后合并
- 状态派生：从历史中派生会话状态

使用场景：
- 编排器在节点执行后更新状态
- 将 Agent 输出合并到全局状态

State transition service for LangGraph runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.runtime.langgraph.state import (
    flatten_structured_overrides,
    flatten_structured_state_view,
)
from app.runtime.messages import AgentEvidence


@dataclass
class StateTransitionService:
    """
    状态转换服务。

    它的职责是把“单个节点的局部返回值”稳定地合并回整场会话状态。
    关键设计不是简单的 `dict.update`，而是：
    - 消息优先投影
    - 历史卡片与消息卡片的合并
    - 结构化状态视图的持续刷新
    """

    dedupe_new_messages: Callable[[List[Any], List[Any]], List[Any]]
    message_deltas_from_cards: Callable[[List[AgentEvidence]], List[Any]]
    derive_conversation_state: Callable[..., Dict[str, Any]]
    messages_to_cards: Callable[[List[Any]], List[AgentEvidence]]
    merge_round_and_message_cards: Callable[[List[AgentEvidence], List[AgentEvidence]], List[AgentEvidence]]
    structured_snapshot: Callable[[Dict[str, Any]], Dict[str, Any]]

    def apply_step_result(
        self,
        state: Dict[str, Any],
        result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        应用步骤结果到状态

        将节点执行结果合并到全局状态。

        流程：
        1. 展平结构和覆盖层
        2. 合并消息（去重）
        3. 投影历史卡片（消息优先）
        4. 派生会话状态
        5. 更新步数计数

        Args:
            state: 当前状态
            result: 节点执行结果

        Returns:
            Dict[str, Any]: 更新后的状态增量
        """
        # 先把当前状态和节点返回值都展平成统一视图，避免嵌套结构和覆盖层互相打架。
        base_state = flatten_structured_state_view(state or {})
        result_payload = dict(result or {})
        result_overrides = flatten_structured_overrides(result_payload)

        # 当前状态里同时维护“消息流”和“历史卡片”两套视角，后面要同步刷新两者。
        current_messages = list(state.get("messages") or [])
        prev_history_cards = list(base_state.get("history_cards") or [])

        # 如果节点显式返回 history_cards，就认为它要覆盖当前 round cards；
        # 否则沿用旧值，再靠消息投影补增量。
        has_history_update = "history_cards" in result_overrides
        next_history_cards = (
            list(result_overrides.get("history_cards") or [])
            if has_history_update
            else prev_history_cards
        )
        new_cards = next_history_cards[len(prev_history_cards):]

        # 节点可以直接产出 messages，也可以只产出 round cards。
        # 如果只有 cards，就从 cards 派生消息增量，保证前端对话流不断裂。
        explicit_messages = list(result_payload.get("messages") or [])
        derived_messages = self.message_deltas_from_cards(new_cards) if not explicit_messages else []
        new_messages = explicit_messages or derived_messages
        deduped_messages = self.dedupe_new_messages(current_messages, new_messages)
        merged_messages = current_messages + list(deduped_messages or [])

        # 最终 history_cards 不是简单沿用节点返回值，而是“回合卡片 + 消息卡片”的合并视图。
        message_cards = self.messages_to_cards(merged_messages)
        projected_history_cards = self.merge_round_and_message_cards(next_history_cards, message_cards)

        # discussion_step_count 既可以由新 card 推进，也可以由纯消息节点推进。
        step_delta = len(new_cards)
        if step_delta <= 0 and deduped_messages:
            # 如果节点只产生了消息，保持进度推进
            step_delta = 1

        # 重新派生会话级聚合状态，例如 agent_outputs、claims、open_questions 等。
        convo_state = self.derive_conversation_state(
            projected_history_cards,
            messages=merged_messages,
            existing_agent_outputs=dict(base_state.get("agent_outputs") or {}),
        )

        # 这里返回的是“下一状态增量”，最终由 orchestrator 再和全局状态合并。
        next_state = {
            **result_payload,
            **result_overrides,
            "next_step": "",
            "history_cards": projected_history_cards,
            "discussion_step_count": int(base_state.get("discussion_step_count") or 0) + step_delta,
            **({"messages": deduped_messages} if deduped_messages else {}),
            **convo_state,
        }

        # 中文注释：这里不能再把原始 state 里的 routing_state / output_state
        # 直接带进快照预览，否则旧的结构化字段会在 flatten 阶段反向覆盖
        # 本轮刚算出的 flat 更新，导致 next_step / discussion_step_count /
        # history_cards 等关键字段“看起来被更新了”，但下一节点读取时仍是旧值。
        # 因此快照基准必须使用已经展平过的最新视图，再叠加本步更新。
        merged_preview = {**base_state, **next_state}
        return {**next_state, **self.structured_snapshot(merged_preview)}
