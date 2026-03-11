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

    @staticmethod
    def _agent_context_envelope(
        *,
        context: Dict[str, Any],
        peer_items: Optional[List[Dict[str, Any]]] = None,
        inbox_messages: Optional[List[Dict[str, Any]]] = None,
        work_log_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """为专家 Agent 构建显式上下文 envelope，兼容旧字段同时新增分层视图。"""
        payload = dict(context or {})
        if "shared_context" not in payload or not isinstance(payload.get("shared_context"), dict):
            payload["shared_context"] = dict(context or {})
        if peer_items is not None:
            payload["peer_context"] = list(peer_items or [])
        if inbox_messages is not None:
            payload["mailbox_context"] = list(inbox_messages or [])
        if work_log_context is not None:
            payload["work_log_context"] = dict(work_log_context or {})
        return payload

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
            context=self._compact_commander_context(context, loop_round=loop_round),
            history_cards=history_cards,
            skill_context=build_rca_skill_context(context=context, loop_round=loop_round, max_rounds=self._max_rounds),
            work_log_context=work_log_context,
            peer_items=peer_items,
            dialogue_items=dialogue_items,
            to_json=self._to_json,
        )

    def _compact_commander_context(self, context: Dict[str, Any], *, loop_round: int) -> Dict[str, Any]:
        """
        为 commander 首轮拆解裁剪上下文，避免把责任田和 incident 全量对象整包塞进首轮 prompt。

        commander 首轮最重要的是：
        - incident 核心摘要
        - 责任田映射出的关键接口 / 表 / 服务 / 代码线索
        - 当前允许调度的 analysis agents
        其它长尾字段留给后续专家 Agent 在各自 prompt 中消费。
        """
        if not isinstance(context, dict):
            return {}

        incident = context.get("incident") if isinstance(context.get("incident"), dict) else {}
        incident_summary = context.get("incident_summary") if isinstance(context.get("incident_summary"), dict) else {}
        mapping = context.get("interface_mapping") if isinstance(context.get("interface_mapping"), dict) else {}
        leads = context.get("investigation_leads") if isinstance(context.get("investigation_leads"), dict) else {}
        available_agents = list(context.get("available_analysis_agents") or [])[:10]
        if not available_agents and isinstance(context.get("parallel_analysis_agents"), list):
            available_agents = list(context.get("parallel_analysis_agents") or [])[:10]

        compact: Dict[str, Any] = {
            "incident_summary": {
                "title": str((incident or {}).get("title") or incident_summary.get("title") or context.get("title") or "")[:160],
                "description": str((incident or {}).get("description") or incident_summary.get("description") or context.get("description") or "")[:280],
                "severity": str((incident or {}).get("severity") or incident_summary.get("severity") or context.get("severity") or ""),
                "service_name": str((incident or {}).get("service_name") or incident_summary.get("service_name") or context.get("service_name") or ""),
            },
            "log_excerpt": str(context.get("log_excerpt") or "")[:320],
            "available_analysis_agents": available_agents,
            "execution_mode": str(context.get("execution_mode") or ""),
        }

        if mapping:
            compact["interface_mapping"] = {
                "matched": bool(mapping.get("matched")),
                "confidence": mapping.get("confidence"),
                "domain": str(mapping.get("domain") or "")[:80],
                "aggregate": str(mapping.get("aggregate") or "")[:80],
                "owner_team": str(mapping.get("owner_team") or "")[:80],
                "owner": str(mapping.get("owner") or "")[:80],
                "endpoint": mapping.get("matched_endpoint") or mapping.get("endpoint") or {},
                "database_tables": list(mapping.get("database_tables") or mapping.get("db_tables") or [])[:8],
                "code_artifacts": list(mapping.get("code_artifacts") or [])[:5],
                "dependency_services": list(mapping.get("dependency_services") or [])[:6],
                "monitor_items": list(mapping.get("monitor_items") or [])[:6],
            }

        if leads:
            compact["investigation_leads"] = {
                "api_endpoints": list(leads.get("api_endpoints") or [])[:4],
                "service_names": list(leads.get("service_names") or [])[:6],
                "code_artifacts": list(leads.get("code_artifacts") or [])[:6],
                "class_names": list(leads.get("class_names") or [])[:6],
                "database_tables": list(leads.get("database_tables") or [])[:8],
                "monitor_items": list(leads.get("monitor_items") or [])[:6],
                "dependency_services": list(leads.get("dependency_services") or [])[:6],
                "trace_ids": list(leads.get("trace_ids") or [])[:4],
                "error_keywords": list(leads.get("error_keywords") or [])[:6],
                "domain": str(leads.get("domain") or "")[:80],
                "aggregate": str(leads.get("aggregate") or "")[:80],
            }

        # 首轮 commander 只需要最小摘要；后续轮次再允许看完整一点的上下文。
        if loop_round > 1:
            compact["existing_agent_outputs"] = context.get("existing_agent_outputs") or {}

        return compact

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
        context_envelope = self._agent_context_envelope(
            context=context,
            peer_items=peer_items,
            inbox_messages=inbox_messages,
            work_log_context=work_log_context,
        )
        return build_peer_driven_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context_envelope,
            skill_context=build_rca_skill_context(
                context=dict(context_envelope.get("shared_context") or {}),
                loop_round=loop_round,
                max_rounds=self._max_rounds,
            ),
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
        context_envelope = self._agent_context_envelope(
            context=context,
            inbox_messages=inbox_messages,
            work_log_context=work_log_context,
        )
        return build_agent_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            max_history_items=self._max_history_items,
            context=context_envelope,
            skill_context=build_rca_skill_context(
                context=dict(context_envelope.get("shared_context") or {}),
                loop_round=loop_round,
                max_rounds=self._max_rounds,
            ),
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
        envelope_peer_items = peer_items_for_collaboration_prompt(
            spec_name=spec.name,
            peer_cards=peer_cards,
            dialogue_items=dialogue_items or [],
            limit=max(2, len(peer_cards) if peer_cards else 2),
        )
        context_envelope = self._agent_context_envelope(
            context=context,
            peer_items=envelope_peer_items,
            inbox_messages=inbox_messages,
            work_log_context=work_log_context,
        )
        return build_collaboration_prompt(
            spec=spec,
            loop_round=loop_round,
            max_rounds=self._max_rounds,
            context=context_envelope,
            skill_context=build_rca_skill_context(
                context=dict(context_envelope.get("shared_context") or {}),
                loop_round=loop_round,
                max_rounds=self._max_rounds,
            ),
            peer_cards=peer_cards,
            peer_items=envelope_peer_items,
            assigned_command=assigned_command,
            work_log_context=work_log_context,
            dialogue_items=dialogue_items,
            inbox_items=inbox_messages,
            to_json=self._to_json,
        )


__all__ = ["PromptBuilder"]
