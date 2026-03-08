"""
运行时 Prompt 组装中心。

这个模块不定义具体 Prompt 模板，而是负责把运行时已有的上下文素材
整理成各类 Prompt 模板需要的输入，例如历史卡片、对话摘要、同伴结论、
工作日志和 Skill 上下文。这样可以把“上下文拼装策略”和“模板正文”拆开维护。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.runtime.langgraph.context_builders import (
    collect_peer_items_from_cards,
    collect_peer_items_from_dialogue,
    coordination_peer_items,
    history_items_for_agent_prompt,
    peer_items_for_collaboration_prompt,
    supervisor_recent_messages,
)
from app.runtime.langgraph.rca_skill import build_rca_skill_context
from app.runtime.langgraph.prompts import (
    PROMPT_TEMPLATE_VERSION,
    build_agent_prompt,
    build_collaboration_prompt,
    build_peer_driven_prompt,
    build_problem_analysis_commander_prompt,
    build_problem_analysis_supervisor_prompt,
)
from app.runtime.langgraph.state import AgentSpec
from app.runtime.messages import AgentEvidence


class PromptBuilder:
    """
    统一封装运行时 Prompt 组装入口。

    orchestrator 只需要调用这里的统一方法，不必关心每类 Prompt
    应该取哪些历史、对话和技能上下文。
    """

    def __init__(
        self,
        *,
        max_rounds: int,
        max_history_items: int,
        to_json: Callable[[Any], str],
        derive_conversation_state_with_context: Callable[..., Dict[str, Any]],
        template_version: str = PROMPT_TEMPLATE_VERSION,
    ) -> None:
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._max_rounds = int(max_rounds or 1)
        self._max_history_items = int(max_history_items or 2)
        self._to_json = to_json
        self._derive_conversation_state_with_context = derive_conversation_state_with_context
        self._template_version = str(template_version or PROMPT_TEMPLATE_VERSION)

    @property
    def template_version(self) -> str:
        """返回当前运行时正在使用的 Prompt 模板版本号。"""
        return self._template_version

    def build_commander_prompt(
        self,
        *,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        work_log_context: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """
        构建主 Agent 的 commander prompt。

        这里重点准备的是“最近同伴结论摘要”，让主 Agent 先看当前证据面，
        再决定要把问题分发给哪些专家。
        """
        # commander 关心的是“最近有哪些专家已经说过什么”，
        # 所以优先抽 peer_items，而不是把全量历史原封不动塞进 Prompt。
        peer_items = coordination_peer_items(
            history_cards=history_cards,
            dialogue_items=dialogue_items or [],
            existing_agent_outputs=existing_agent_outputs or {},
            limit=8,
        )
        return build_problem_analysis_commander_prompt(
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context,
            history_cards=history_cards,
            skill_context=build_rca_skill_context(context=context, loop_round=loop_round, max_rounds=self._max_rounds),
            work_log_context=work_log_context,
            peer_items=peer_items,
            dialogue_items=dialogue_items,
            to_json=self._to_json,
        )

    def build_supervisor_prompt(
        self,
        *,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        round_history_cards: List[AgentEvidence],
        discussion_step_count: int,
        max_discussion_steps: int,
        work_log_context: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        existing_agent_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """
        构建主 Agent 的 supervisor prompt。

        这一层不是做首轮任务拆解，而是做讨论过程中的动态调度：
        它需要知道最近发言、未决问题和讨论步数预算，判断下一步继续补证还是收口。
        """
        # supervisor prompt 会显式携带 open_questions 和 recent_messages，
        # 避免模型在长历史里自己猜“目前还缺什么”。
        convo_state = self._derive_conversation_state_with_context(
            history_cards,
            messages=[],
            existing_agent_outputs=existing_agent_outputs or {},
        )
        return build_problem_analysis_supervisor_prompt(
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context,
            round_history_cards=round_history_cards,
            skill_context=build_rca_skill_context(context=context, loop_round=loop_round, max_rounds=self._max_rounds),
            work_log_context=work_log_context,
            recent_messages=supervisor_recent_messages(
                round_history_cards=round_history_cards,
                dialogue_items=dialogue_items or [],
                limit=10,
            ),
            open_questions=convo_state.get("open_questions") or [],
            dialogue_items=dialogue_items,
            discussion_step_count=discussion_step_count,
            max_discussion_steps=max_discussion_steps,
            to_json=self._to_json,
        )

    def build_peer_driven_prompt(
        self,
        *,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        work_log_context: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        构建基于同伴结论驱动的 Prompt。

        这种 Prompt 主要用于需要直接回应他人观点的场景，优先从对话流里抽 peer items；
        如果对话流不足，再退回历史卡片。
        """
        peer_items = collect_peer_items_from_dialogue(
            dialogue_items or [],
            exclude_agent=spec.name,
            limit=max(2, self._max_history_items + 1),
        )
        if len(peer_items) < 2:
            # 对话流不足时，退回卡片视图兜底，避免 peer-driven prompt 失去参考对象。
            fallback_peers = collect_peer_items_from_cards(
                history_cards,
                exclude_agent=spec.name,
                limit=max(2, self._max_history_items + 1),
            )
            known = {(str(i.get("agent") or ""), str(i.get("conclusion") or "")) for i in peer_items}
            for item in fallback_peers:
                sig = (str(item.get("agent") or ""), str(item.get("conclusion") or ""))
                if sig in known:
                    continue
                peer_items.append(item)
                known.add(sig)
                if len(peer_items) >= max(2, self._max_history_items + 1):
                    break
        return build_peer_driven_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context,
            skill_context=build_rca_skill_context(context=context, loop_round=loop_round, max_rounds=self._max_rounds),
            peer_items=peer_items,
            assigned_command=assigned_command,
            work_log_context=work_log_context,
            dialogue_items=dialogue_items,
            inbox_items=inbox_messages,
            to_json=self._to_json,
        )

    def build_agent_prompt(
        self,
        *,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        work_log_context: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        构建普通专家 Agent 的执行 Prompt。

        这里会同时带入命令、责任田与工具上下文、最近历史摘要以及 inbox 消息，
        让专家 Agent 在单轮内完成“读命令 -> 看线索 -> 输出结构化结果”。
        """
        return build_agent_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            max_history_items=self._max_history_items,
            context=context,
            skill_context=build_rca_skill_context(context=context, loop_round=loop_round, max_rounds=self._max_rounds),
            history_cards=history_cards,
            history_items=history_items_for_agent_prompt(
                agent_name=spec.name,
                history_cards=history_cards,
                dialogue_items=dialogue_items or [],
                limit=max(1, self._max_history_items),
            ),
            assigned_command=assigned_command,
            work_log_context=work_log_context,
            dialogue_items=dialogue_items,
            inbox_items=inbox_messages,
            to_json=self._to_json,
        )

    def build_collaboration_prompt(
        self,
        *,
        spec: AgentSpec,
        loop_round: int,
        context: Dict[str, Any],
        peer_cards: List[AgentEvidence],
        assigned_command: Optional[Dict[str, Any]] = None,
        work_log_context: Optional[Dict[str, Any]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        构建协作阶段 Prompt。

        协作阶段不再让 Agent 重做完整分析，而是围绕 peer_cards 和同伴摘要，
        让专家基于他人的观点补证、反驳或收敛。
        """
        return build_collaboration_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context,
            skill_context=build_rca_skill_context(context=context, loop_round=loop_round, max_rounds=self._max_rounds),
            peer_cards=peer_cards,
            peer_items=peer_items_for_collaboration_prompt(
                spec_name=spec.name,
                peer_cards=peer_cards,
                dialogue_items=dialogue_items or [],
                limit=max(2, len(peer_cards) if peer_cards else 2),
            ),
            assigned_command=assigned_command,
            work_log_context=work_log_context,
            dialogue_items=dialogue_items,
            inbox_items=inbox_messages,
            to_json=self._to_json,
        )


__all__ = ["PromptBuilder"]
