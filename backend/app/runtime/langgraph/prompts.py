"""
LangGraph 运行时 Prompt 模板与结构化输出 Schema 定义。

这个文件关注“Prompt 本身长什么样”，不处理运行时上下文选择逻辑。
上层 `PromptBuilder` 负责准备输入，这里负责把输入组织成最终文本模板。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.runtime.langgraph.state import AgentSpec
from app.runtime.messages import AgentEvidence

ToJsonFn = Callable[[Any], str]
PROMPT_TEMPLATE_VERSION = "lg-rca-prompt-v2.2.0"

_STRICT_OUTPUT_RULES = (
    "输出协议：\n"
    "1) 只输出一个 JSON 对象；\n"
    "2) chat_message 用自然语言短句；\n"
    "3) 证据不足时降低 confidence（<=0.55）并补 next_checks；若共享上下文已给出明确日志/代码/数据库证据，可保留中等置信度（0.56~0.75），但必须写清受限边界；\n"
    "4) 有冲突证据时写 counter_evidence。\n"
)


def _tool_limited_instruction(context: Dict[str, Any], *, to_json: ToJsonFn) -> str:
    """
    为工具受限场景追加专门的提示片段。

    目标是强制模型区分“已真实取证”和“仅基于已有证据做受限分析”，
    避免工具不可用时仍写出看似已验证的结论。
    """
    tool_ctx = context.get("tool_context")
    if not isinstance(tool_ctx, dict):
        return ""
    command_gate = tool_ctx.get("command_gate")
    if not isinstance(command_gate, dict):
        command_gate = {}
    if not bool(command_gate.get("has_command")) or not bool(command_gate.get("allow_tool")):
        return ""
    status = str(tool_ctx.get("status") or "").strip().lower()
    used = bool(tool_ctx.get("used"))
    if used and status == "ok":
        return ""
    if status not in {"disabled", "unavailable", "error", "failed", "timeout"}:
        return ""
    limited_ctx = {
        "tool_name": str(tool_ctx.get("name") or ""),
        "tool_status": status,
        "summary": str(tool_ctx.get("summary") or "")[:240],
        "missing_evidence_hint": "继续基于已有证据推理，但必须明确哪些证据尚未通过工具采集到。",
    }
    return (
        "工具受限说明：\n"
        "当前命令允许你使用工具，但工具不可用。你仍然必须基于现有证据完成分析，"
        "同时在 analysis/conclusion/next_checks 中明确写出缺失证据和后续补采动作。\n"
        "如果 shared_context / focused_context 已经提供了明确日志、代码 diff、数据库等待或指标证据，"
        "不要机械把 confidence 压到 0.45；应把它写成“基于已提供证据的受限但可用结论”。\n"
        "不要假装已经完成实时取证，不要把受限推理包装成已验证结论。\n"
        f"```json\n{to_json(limited_ctx)}\n```\n\n"
    )


def _focused_context_block(context: Dict[str, Any], *, to_json: ToJsonFn) -> str:
    """把 Agent 专属分析上下文单独展示，避免模型只盯着粗粒度全局摘要。"""
    focused = context.get("focused_context")
    if not isinstance(focused, dict) or not focused:
        return ""
    return f"Agent 专属分析上下文：\n```json\n{to_json(focused)}\n```\n\n"


def _agent_local_context_block(context: Dict[str, Any], *, to_json: ToJsonFn) -> str:
    """把当前 Agent 的私有工作记忆单独展示，避免误当成全局共识。"""
    local_ctx = context.get("agent_local_context")
    if not isinstance(local_ctx, dict) or not local_ctx:
        return ""
    return f"Agent 私有工作记忆：\n```json\n{to_json(local_ctx)}\n```\n\n"


def _shared_context_payload(context: Dict[str, Any]) -> Dict[str, Any]:
    """提取专家 Prompt 可见的共享上下文，避免直接倾倒原始 incident 全量对象。"""
    if not isinstance(context, dict):
        return {}
    shared = context.get("shared_context")
    if isinstance(shared, dict) and shared:
        return shared
    hidden_keys = {
        "shared_context",
        "focused_context",
        "tool_context",
        "peer_context",
        "mailbox_context",
        "work_log_context",
        "agent_local_context",
        "incident",
        "context",
    }
    return {
        str(key): value
        for key, value in context.items()
        if str(key) not in hidden_keys
    }


def _shared_context_block(context: Dict[str, Any], *, to_json: ToJsonFn) -> str:
    """把共享上下文单独展示，并明确这是裁剪后的会话摘要。"""
    shared = _shared_context_payload(context)
    if not shared:
        return ""
    return f"共享上下文：\n```json\n{to_json(shared)}\n```\n\n"


def _independent_first_analysis(spec: AgentSpec) -> bool:
    """判断当前 Agent 是否应先做独立取证，再进入同伴观点对照。"""
    if str(spec.phase or "").strip().lower() != "analysis":
        return False
    return str(spec.name or "").strip() not in {
        "ProblemAnalysisAgent",
        "CriticAgent",
        "RebuttalAgent",
        "JudgeAgent",
        "VerificationAgent",
    }


def coordinator_command_schema() -> Dict[str, Any]:
    """定义主 Agent / supervisor 共用的协调输出 Schema。"""
    return {
        "chat_message": "",
        "analysis": "",
        "conclusion": "",
        "selected_agents": [
            "LogAgent|DomainAgent|CodeAgent|DatabaseAgent|MetricsAgent|ImpactAnalysisAgent|ChangeAgent|RunbookAgent|RuleSuggestionAgent|"
            "CriticAgent|RebuttalAgent|JudgeAgent|VerificationAgent"
        ],
        "next_mode": "parallel_analysis|single|judge|stop",
        "next_agent": (
            "LogAgent|DomainAgent|CodeAgent|DatabaseAgent|MetricsAgent|ImpactAnalysisAgent|ChangeAgent|RunbookAgent|RuleSuggestionAgent|"
            "CriticAgent|RebuttalAgent|JudgeAgent|VerificationAgent"
        ),
        "should_stop": False,
        "stop_reason": "",
        "should_pause_for_review": False,
        "review_reason": "",
        "review_payload": {"risk_level": "", "decision_basis": [], "operator_hint": ""},
        "commands": [
            {
                "target_agent": (
                    "LogAgent|DomainAgent|CodeAgent|DatabaseAgent|MetricsAgent|ImpactAnalysisAgent|ChangeAgent|RunbookAgent|RuleSuggestionAgent|"
                    "CriticAgent|RebuttalAgent|JudgeAgent|VerificationAgent"
                ),
                "task": "",
                "focus": "",
                "expected_output": "",
                "use_tool": True,
                "database_tables": [],
                "skill_hints": [],
                "tool_hints": [],
            }
        ],
        "evidence_chain": [""],
        "confidence": 0.0,
    }


def judge_output_schema() -> Dict[str, Any]:
    """定义 JudgeAgent 的最终裁决输出 Schema。"""
    return {
        "chat_message": "",
        "final_judgment": {
            "root_cause": {"summary": "", "category": "", "confidence": 0.0},
            "evidence_chain": [
                {
                    "evidence_id": "evd_xxx",
                    "type": "log|code|domain|metrics",
                    "description": "",
                    "source": "",
                    "source_ref": "",
                    "location": "",
                    "strength": "strong|medium|weak",
                }
            ],
            "fix_recommendation": {
                "summary": "",
                "steps": [],
                "code_changes_required": True,
            },
            "impact_analysis": {
                "affected_services": [],
                "affected_functions": [
                    {
                        "name": "",
                        "severity": "critical|high|medium|low",
                        "affected_interfaces": [],
                        "evidence_basis": [],
                        "user_impact": {
                            "measured_users": None,
                            "estimated_users": None,
                            "affected_ratio": "",
                            "estimation_basis": "",
                            "confidence": 0.0,
                        },
                    }
                ],
                "affected_interfaces": [
                    {
                        "endpoint": "",
                        "method": "",
                        "service": "",
                        "error_signal": "",
                        "related_function": "",
                        "user_impact": {
                            "measured_users": None,
                            "estimated_users": None,
                            "confidence": 0.0,
                        },
                    }
                ],
                "affected_user_scope": {
                    "measured_users": None,
                    "estimated_users": None,
                    "affected_ratio": "",
                    "estimation_basis": "",
                    "confidence": 0.0,
                },
                "business_impact": "",
                "affected_users": "",
                "unknowns": [],
            },
            "risk_assessment": {
                "risk_level": "critical|high|medium|low",
                "risk_factors": [],
            },
        },
        "alternatives": [
            {"candidate": "", "why_not_selected": "", "confidence": 0.0}
        ],
        "decision_rationale": {"key_factors": [], "reasoning": ""},
        "action_items": [],
        "responsible_team": {"team": "", "owner": ""},
        "confidence": 0.0,
    }


def verification_output_schema() -> Dict[str, Any]:
    """定义 VerificationAgent 的验证计划输出 Schema。"""
    return {
        "chat_message": "",
        "analysis": "",
        "conclusion": "",
        "verification_plan": [
            {
                "id": "ver_1",
                "dimension": "functional|performance|regression|rollback",
                "objective": "",
                "steps": [""],
                "pass_criteria": "",
                "owner": "",
                "priority": "p0|p1|p2",
                "rollback_trigger": "",
            }
        ],
        "confidence": 0.0,
    }


def build_problem_analysis_commander_prompt(
    *,
    loop_round: int,
    max_rounds: int,
    context: Dict[str, Any],
    history_cards: Optional[List[AgentEvidence]] = None,
    skill_context: Optional[Dict[str, Any]] = None,
    work_log_context: Optional[Dict[str, Any]] = None,
    peer_items: Optional[List[Dict[str, Any]]] = None,
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    """
    生成主 Agent 的命令分发 Prompt。

    这个模板同时要求自然语言 chat_message 和结构化 commands，
    目的是兼顾前端可读性与系统可编排性。
    """
    if peer_items is None:
        if dialogue_items:
            peer_items = [
                {
                    "agent": str(item.get("agent_name") or item.get("agent") or "unknown"),
                    "phase": str(item.get("phase") or ""),
                    "summary": str(item.get("message") or item.get("summary") or "")[:120],
                    "confidence": round(float(item.get("confidence") or 0.0), 3),
                }
                for item in (dialogue_items or [])[-8:]
                if isinstance(item, dict)
            ]
        else:
            peer_items = [
                {
                    "agent": card.agent_name,
                    "phase": card.phase,
                    "summary": card.summary[:100],
                    "confidence": round(float(card.confidence or 0.0), 3),
                }
                for card in (history_cards or [])[-4:]
            ]
    schema = coordinator_command_schema()
    dialogue_block = ""
    if dialogue_items:
        dialogue_block = f"\n最近对话消息:\n```json\n{to_json(dialogue_items[-4:])}\n```\n"
    work_log_block = ""
    if work_log_context:
        work_log_block = f"\n工作日志上下文:\n```json\n{to_json(work_log_context)}\n```\n"
    skill_block = ""
    if skill_context:
        skill_block = f"\nRCA 技能模板与场景参数:\n```json\n{to_json(skill_context)}\n```\n"
    return (
        f"你是问题分析主Agent。当前第 {loop_round}/{max_rounds} 轮。\n"
        "请先给出一段简短会议发言(chat_message)，然后给出对各专家Agent的命令清单(commands)。\n"
        "同时你需要决定下一步调度：selected_agents/next_mode/next_agent；如果你判断证据充分可以停止，设置 should_stop=true 并给出 stop_reason。\n"
        "selected_agents 必须填写本轮真正需要执行的专家集合，且应优先从故障上下文中的 available_analysis_agents 里选择；"
        "若已存在历史结论，可补充 CriticAgent/RebuttalAgent/JudgeAgent/VerificationAgent 命令。\n"
        "若 context.interface_mapping.database_tables 非空，必须把这些表名填入 DatabaseAgent 命令的 database_tables 字段。\n"
        "必要时可在命令中提供 skill_hints（技能名数组），指导专家Agent优先使用指定技能模板。\n"
        "若需要调用扩展插件工具，可同时提供 tool_hints（工具ID数组，例如 ['design_spec_alignment']）。\n"
        "命令要具体到分析重点，不要泛泛而谈；selected_agents 必须与 commands 对齐，不要点名未下发命令的专家。\n"
        "禁止输出 Markdown 表格、章节标题、解释性散文或代码块包裹的伪 JSON；只允许输出一个 JSON 对象。\n"
        "若你无法完全确定全部字段，也必须先输出最小可执行 commands，而不是输出说明文档。\n\n"
        f"故障上下文:\n```json\n{to_json(context)}\n```\n\n"
        f"{dialogue_block}"
        f"{skill_block}"
        f"{work_log_block}"
        f"最近发言摘要:\n```json\n{to_json(peer_items[-5:])}\n```\n\n"
        f"{_STRICT_OUTPUT_RULES}\n"
        f"仅输出 JSON，格式:\n```json\n{to_json(schema)}\n```"
    )


def build_problem_analysis_supervisor_prompt(
    *,
    loop_round: int,
    max_rounds: int,
    context: Dict[str, Any],
    round_history_cards: Optional[List[AgentEvidence]] = None,
    skill_context: Optional[Dict[str, Any]] = None,
    work_log_context: Optional[Dict[str, Any]] = None,
    recent_messages: Optional[List[Dict[str, Any]]] = None,
    open_questions: List[str],
    discussion_step_count: int,
    max_discussion_steps: int,
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    """
    生成 supervisor 路由 Prompt。

    它和 commander prompt 的区别在于：
    - commander 负责首轮任务拆解
    - supervisor 负责讨论过程中的下一步调度和收口判断
    """
    if recent_messages is None:
        if dialogue_items:
            recent_messages = [
                {
                    "agent": str(item.get("agent_name") or item.get("agent") or "unknown"),
                    "phase": str(item.get("phase") or ""),
                    "conclusion": str(item.get("message") or item.get("conclusion") or "")[:160],
                    "confidence": round(float(item.get("confidence") or 0.0), 3),
                }
                for item in (dialogue_items or [])[-10:]
                if isinstance(item, dict)
            ]
        else:
            recent_messages = [
                {
                    "agent": card.agent_name,
                    "phase": card.phase,
                    "conclusion": card.conclusion[:160],
                    "confidence": round(float(card.confidence or 0.0), 3),
                }
                for card in (round_history_cards or [])[-6:]
            ]
    schema = coordinator_command_schema()
    dialogue_block = ""
    if dialogue_items:
        dialogue_block = f"\n最近对话消息:\n```json\n{to_json(dialogue_items[-5:])}\n```\n"
    work_log_block = ""
    if work_log_context:
        work_log_block = f"\n工作日志上下文:\n```json\n{to_json(work_log_context)}\n```\n"
    skill_block = ""
    if skill_context:
        skill_block = f"\nRCA 技能模板与场景参数:\n```json\n{to_json(skill_context)}\n```\n"
    return (
        f"你是问题分析主Agent，正在主持故障分析讨论。当前第 {loop_round}/{max_rounds} 轮。\n"
        "请像会议主持人一样决定下一位发言者或停止讨论。你必须输出 JSON。\n"
        "规则：\n"
        "1) 优先让Agent回应他人观点而不是重复自己的完整分析；\n"
        "2) 若证据不足，继续调度某个专家发言并下达具体命令；\n"
        "3) 若你判断结论已充分，设置 should_stop=true；但若尚未形成裁决，next_agent 应为 JudgeAgent。\n"
        "4) selected_agents 必须列出本步计划执行的Agent（1-3个），commands 也只给这些Agent下命令。\n\n"
        "5) 若 context.interface_mapping.database_tables 非空，DatabaseAgent 命令必须带 database_tables。\n\n"
        "6) 如需强制某专家按特定技能模板分析，可填写 skill_hints（例如 ['log-forensics']）。\n\n"
        "7) 如需调用扩展插件工具，可填写 tool_hints（例如 ['design_spec_alignment']）。\n\n"
        "8) 若 context.deployment_profile.name=production_governed 且你认为结论可用但仍需人工确认，可设置 should_pause_for_review=true，并填写 review_reason 与 review_payload；此时不要设置 should_stop=true。\n\n"
        f"讨论步数预算: {discussion_step_count}/{max_discussion_steps}\n"
        f"故障上下文:\n```json\n{to_json(context)}\n```\n\n"
        f"{dialogue_block}"
        f"{skill_block}"
        f"{work_log_block}"
        f"本轮最近发言:\n```json\n{to_json(recent_messages)}\n```\n\n"
        f"未决问题:\n```json\n{to_json(open_questions[:8])}\n```\n\n"
        f"{_STRICT_OUTPUT_RULES}\n"
        f"输出 JSON 格式:\n```json\n{to_json(schema)}\n```"
    )


def build_agent_prompt(
    *,
    spec: AgentSpec,
    loop_round: int,
    max_rounds: int,
    max_history_items: int,
    context: Dict[str, Any],
    skill_context: Optional[Dict[str, Any]] = None,
    history_cards: Optional[List[AgentEvidence]] = None,
    history_items: Optional[List[Dict[str, Any]]] = None,
    assigned_command: Optional[Dict[str, Any]],
    work_log_context: Optional[Dict[str, Any]] = None,
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    inbox_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    """
    生成普通专家 Agent 的单轮执行 Prompt。

    模板目标是把命令、工具上下文、历史摘要、收件箱消息和输出协议
    放在一个稳定结构里，减少不同 Agent 之间的 Prompt 漂移。
    """
    if history_items is None:
        # 没有上层预处理摘要时，这里退回到对话流或历史卡片做本地兜底。
        history_items = []
        for item in (dialogue_items or [])[-8:]:
            if not isinstance(item, dict):
                continue
            history_items.append(
                {
                    "agent": str(item.get("agent_name") or item.get("agent") or "unknown"),
                    "phase": str(item.get("phase") or ""),
                    "summary": str(item.get("message") or item.get("summary") or "")[:140],
                    "confidence": round(float(item.get("confidence") or 0.0), 3),
                }
            )
        if not history_items:
            history_items = [
                {
                    "agent": card.agent_name,
                    "phase": card.phase,
                    "summary": card.summary[:120],
                    "conclusion": card.conclusion[:140],
                    "confidence": round(float(card.confidence or 0.0), 3),
                }
                for card in (history_cards or [])[-min(max_history_items, 4):]
            ]
    output_schema = (
        judge_output_schema()
        if spec.name == "JudgeAgent"
        else verification_output_schema()
        if spec.name == "VerificationAgent"
        else _normal_output_schema()
    )
    output_constraints = (
        "action_items 最多 3 条，decision_rationale.reasoning 控制在 120 字内。\n\n"
        if spec.name == "JudgeAgent"
        else ""
    )
    command_block = ""
    if assigned_command:
        command_block = (
            f"主Agent命令：\n```json\n{to_json(assigned_command)}\n```\n"
            "必须在 chat_message 中先确认收到命令，并围绕命令重点输出。\n\n"
        )
    dialogue_block = ""
    if dialogue_items:
        dialogue_block = f"最近对话消息：\n```json\n{to_json(dialogue_items[-4:])}\n```\n\n"
    inbox_block = ""
    if inbox_items:
        inbox_block = f"你收到的消息（命令/反馈/证据）：\n```json\n{to_json(inbox_items[-4:])}\n```\n\n"
    work_log_block = ""
    if work_log_context:
        work_log_block = f"工作日志上下文：\n```json\n{to_json(work_log_context)}\n```\n\n"
    skill_block = ""
    if skill_context:
        skill_block = f"RCA 技能模板与场景参数：\n```json\n{to_json(skill_context)}\n```\n\n"
    tool_limited_block = _tool_limited_instruction(context, to_json=to_json)
    focused_block = _focused_context_block(context, to_json=to_json)
    local_block = _agent_local_context_block(context, to_json=to_json)
    shared_block = _shared_context_block(context, to_json=to_json)
    analysis_mode_intro = (
        "先基于你的专属上下文独立取证，再按需要引用最近交互摘要补充或修正判断。\n"
        "优先输出你亲自确认的证据，不要为了迎合同伴而放弃独立判断。\n"
        if _independent_first_analysis(spec)
        else "只需要基于核心观点与结论推理，不要复述全部历史，结论请简短。\n"
    )
    return (
        f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段={spec.phase}。\n"
        f"{analysis_mode_intro}"
        "请以真人讨论口吻在 chat_message 中表达你的发言（1-3句），然后输出 JSON。\n\n"
        f"{_STRICT_OUTPUT_RULES}\n"
        f"{output_constraints}"
        f"{command_block}"
        f"{dialogue_block}"
        f"{inbox_block}"
        f"{skill_block}"
        f"{shared_block}"
        f"{focused_block}"
        f"{local_block}"
        f"{tool_limited_block}"
        f"{work_log_block}"
        f"最近交互摘要：\n```json\n{to_json(history_items[-5:])}\n```\n\n"
        f"请仅输出 JSON，格式示例：\n```json\n{to_json(output_schema)}\n```"
    )


def build_collaboration_prompt(
    *,
    spec: AgentSpec,
    loop_round: int,
    max_rounds: int,
    context: Dict[str, Any],
    skill_context: Optional[Dict[str, Any]] = None,
    peer_cards: Optional[List[AgentEvidence]] = None,
    peer_items: Optional[List[Dict[str, Any]]] = None,
    assigned_command: Optional[Dict[str, Any]],
    work_log_context: Optional[Dict[str, Any]] = None,
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    inbox_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    """
    生成协作阶段 Prompt。

    这类 Prompt 更强调 peer_cards 和 peer_items，让 Agent 在已有结论基础上
    做补充、反驳或校验，而不是重新跑一遍完整排障。
    """
    if peer_items is None:
        peer_items = [
            {
                "agent": card.agent_name,
                "summary": card.summary[:120],
                "conclusion": card.conclusion[:160],
                "confidence": round(float(card.confidence), 3),
            }
            for card in (peer_cards or [])
            if card.agent_name != spec.name
        ]
    command_block = ""
    if assigned_command:
        command_block = (
            f"\n主Agent命令：\n```json\n{to_json(assigned_command)}\n```\n"
            "你需要在 chat_message 中明确这是对主Agent命令的执行反馈。\n"
        )
    dialogue_block = ""
    if dialogue_items:
        dialogue_block = f"最近对话消息：\n```json\n{to_json(dialogue_items[-4:])}\n```\n\n"
    inbox_block = ""
    if inbox_items:
        inbox_block = f"你收到的消息（命令/反馈/证据）：\n```json\n{to_json(inbox_items[-4:])}\n```\n\n"
    work_log_block = ""
    if work_log_context:
        work_log_block = f"工作日志上下文：\n```json\n{to_json(work_log_context)}\n```\n\n"
    skill_block = ""
    if skill_context:
        skill_block = f"RCA 技能模板与场景参数：\n```json\n{to_json(skill_context)}\n```\n\n"
    focused_block = _focused_context_block(context, to_json=to_json)
    local_block = _agent_local_context_block(context, to_json=to_json)
    shared_block = _shared_context_block(context, to_json=to_json)
    return (
        f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段=analysis。\n"
        "现在进入协同复核阶段：你必须基于其他 Agent 的结论进行交叉校验并修正自己的判断。\n"
        "请以真人讨论口吻在 chat_message 中明确你在回应谁、采纳或反驳什么。\n"
        "要求：\n"
        "1) 明确指出至少 1 条你采纳或反驳的同伴结论；\n"
        "2) 在 evidence_chain 中包含同伴观点依据（可写成 peer:<agent_name>:<观点>）；\n"
        "3) 仅输出 JSON，不要解释文本，保持精炼。\n\n"
        f"{_STRICT_OUTPUT_RULES}\n"
        f"{command_block}"
        f"{dialogue_block}"
        f"{inbox_block}"
        f"{skill_block}"
        f"{shared_block}"
        f"{focused_block}"
        f"{local_block}"
        f"{work_log_block}"
        f"同伴结论：\n```json\n{to_json(peer_items[-4:])}\n```\n\n"
        f"输出格式：\n```json\n{to_json(_normal_output_schema())}\n```"
    )


def build_peer_driven_prompt(
    *,
    spec: AgentSpec,
    loop_round: int,
    max_rounds: int,
    context: Dict[str, Any],
    skill_context: Optional[Dict[str, Any]] = None,
    peer_items: List[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
    work_log_context: Optional[Dict[str, Any]] = None,
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    inbox_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    """生成需要直接回应同伴观点的 peer-driven Prompt。"""
    dialogue_block = ""
    if dialogue_items:
        dialogue_block = f"最近对话消息：\n```json\n{to_json(dialogue_items[-5:])}\n```\n\n"
    inbox_block = ""
    if inbox_items:
        inbox_block = f"你收到的消息（命令/反馈/证据）：\n```json\n{to_json(inbox_items[-5:])}\n```\n\n"
    work_log_block = ""
    if work_log_context:
        work_log_block = f"工作日志上下文：\n```json\n{to_json(work_log_context)}\n```\n\n"
    skill_block = ""
    if skill_context:
        skill_block = f"RCA 技能模板与场景参数：\n```json\n{to_json(skill_context)}\n```\n\n"
    focused_block = _focused_context_block(context, to_json=to_json)
    local_block = _agent_local_context_block(context, to_json=to_json)
    shared_block = _shared_context_block(context, to_json=to_json)
    if spec.name == "JudgeAgent":
        command_block = ""
        if assigned_command:
            command_block = (
                f"\n主Agent命令：\n```json\n{to_json(assigned_command)}\n```\n"
                "你必须响应主Agent命令要求并在 chat_message 中体现“已收到命令/正在综合裁决”。\n"
            )
        return (
            f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段={spec.phase}。\n"
            "必须基于其他 Agent 结论进行综合裁决，禁止独立发挥。\n"
            "请用真人开会讨论的口吻在 chat_message 中表达观点（简短、明确引用同伴结论），并输出 JSON。\n"
            "字段尽量精炼，action_items 最多 3 条。\n\n"
            f"{_STRICT_OUTPUT_RULES}\n"
            f"{command_block}"
            f"{dialogue_block}"
            f"{inbox_block}"
            f"{skill_block}"
            f"{shared_block}"
            f"{focused_block}"
            f"{local_block}"
            f"{work_log_block}"
            f"同伴结论：\n```json\n{to_json(peer_items[-5:])}\n```\n\n"
            f"输出格式：\n```json\n{to_json(judge_output_schema())}\n```"
        )

    if spec.name == "VerificationAgent":
        command_block = ""
        if assigned_command:
            command_block = (
                f"\n主Agent命令：\n```json\n{to_json(assigned_command)}\n```\n"
                "你需要先确认收到命令，再输出验证计划。\n"
            )
        return (
            f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段={spec.phase}。\n"
            "请严格基于 Judge 与各专家结论生成验证计划，覆盖功能、性能、回归、回滚四个维度。\n"
            "chat_message 用自然语言简要说明验证策略，然后仅输出 JSON。\n\n"
            f"{_STRICT_OUTPUT_RULES}\n"
            f"{command_block}"
            f"{dialogue_block}"
            f"{inbox_block}"
            f"{skill_block}"
            f"{shared_block}"
            f"{focused_block}"
            f"{local_block}"
            f"{work_log_block}"
            f"同伴结论：\n```json\n{to_json(peer_items[-5:])}\n```\n\n"
            f"输出格式：\n```json\n{to_json(verification_output_schema())}\n```"
        )

    command_block = ""
    if assigned_command:
        command_block = (
            f"\n主Agent命令：\n```json\n{to_json(assigned_command)}\n```\n"
            "你必须先在 chat_message 中确认收到主Agent命令，再给出执行结果。\n"
        )
    if _independent_first_analysis(spec):
        return (
            f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段={spec.phase}。\n"
            "先基于你的专属上下文独立取证，再参考同伴结论判断哪些观点值得采纳、补强或反驳。\n"
            "请以真人讨论口吻在 chat_message 中先说你的独立判断（1-3句），再给结构化字段。\n"
            "要求：\n"
            "1) 优先输出你亲自确认的证据；\n"
            "2) 若引用同伴观点，要明确说明采纳或保留意见；\n"
            "3) 仅输出 JSON，内容尽量简短。\n\n"
            f"{_STRICT_OUTPUT_RULES}\n"
            f"{command_block}"
            f"{dialogue_block}"
            f"{inbox_block}"
            f"{skill_block}"
            f"{shared_block}"
            f"{focused_block}"
            f"{local_block}"
            f"{work_log_block}"
            f"同伴结论（仅供对照）：\n```json\n{to_json(peer_items[-5:])}\n```\n\n"
            f"输出格式：\n```json\n{to_json(_normal_output_schema())}\n```"
        )

    return (
        f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段={spec.phase}。\n"
        "必须基于其他 Agent 的结论进行分析，禁止独立分析。\n"
        "请以真人讨论口吻在 chat_message 中先说结论（1-3句），再给结构化字段。\n"
        "要求：\n"
        "1) 至少明确采纳/反驳 1 条同伴结论；\n"
        "2) evidence_chain 至少包含 1 条 peer:<agent_name>:<观点>；\n"
        "3) 仅输出 JSON，内容尽量简短。\n\n"
        f"{_STRICT_OUTPUT_RULES}\n"
        f"{command_block}"
        f"{dialogue_block}"
        f"{inbox_block}"
        f"{skill_block}"
        f"{shared_block}"
        f"{focused_block}"
        f"{local_block}"
        f"{work_log_block}"
        f"同伴结论：\n```json\n{to_json(peer_items[-5:])}\n```\n\n"
        f"输出格式：\n```json\n{to_json(_normal_output_schema())}\n```"
    )


def _normal_output_schema() -> Dict[str, Any]:
    """返回普通专家 Agent 使用的结构化输出 Schema。"""
    return {
        "chat_message": "",
        "analysis": "",
        "conclusion": "",
        "counter_evidence": [""],
        "next_checks": [""],
        "evidence_chain": [
            {
                "evidence_id": "evd_xxx",
                "type": "log|code|domain|metrics|change|runbook|analysis",
                "description": "",
                "source": "",
                "source_ref": "",
            }
        ],
        "confidence": 0.0,
    }
