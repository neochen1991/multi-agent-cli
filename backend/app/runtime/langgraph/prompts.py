"""Prompt builders and JSON schema templates for LangGraph runtime."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.runtime.langgraph.state import AgentSpec
from app.runtime.messages import AgentEvidence

ToJsonFn = Callable[[Any], str]


def coordinator_command_schema() -> Dict[str, Any]:
    return {
        "chat_message": "",
        "analysis": "",
        "conclusion": "",
        "next_mode": "parallel_analysis|single|judge|stop",
        "next_agent": "LogAgent|DomainAgent|CodeAgent|CriticAgent|RebuttalAgent|JudgeAgent",
        "should_stop": False,
        "stop_reason": "",
        "commands": [
            {
                "target_agent": "LogAgent|DomainAgent|CodeAgent|CriticAgent|RebuttalAgent|JudgeAgent",
                "task": "",
                "focus": "",
                "expected_output": "",
            }
        ],
        "evidence_chain": [""],
        "confidence": 0.0,
    }


def judge_output_schema() -> Dict[str, Any]:
    return {
        "chat_message": "",
        "final_judgment": {
            "root_cause": {"summary": "", "category": "", "confidence": 0.0},
            "evidence_chain": [
                {
                    "type": "log|code|domain|metrics",
                    "description": "",
                    "source": "",
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
                "business_impact": "",
            },
            "risk_assessment": {
                "risk_level": "critical|high|medium|low",
                "risk_factors": [],
            },
        },
        "decision_rationale": {"key_factors": [], "reasoning": ""},
        "action_items": [],
        "responsible_team": {"team": "", "owner": ""},
        "confidence": 0.0,
    }


def build_problem_analysis_commander_prompt(
    *,
    loop_round: int,
    max_rounds: int,
    context: Dict[str, Any],
    history_cards: List[AgentEvidence],
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    peer_items = [
        {
            "agent": card.agent_name,
            "phase": card.phase,
            "summary": card.summary[:100],
            "conclusion": card.conclusion[:120],
            "confidence": round(float(card.confidence or 0.0), 3),
        }
        for card in history_cards[-6:]
    ]
    schema = coordinator_command_schema()
    dialogue_block = ""
    if dialogue_items:
        dialogue_block = f"\n最近对话消息:\n```json\n{to_json(dialogue_items[-8:])}\n```\n"
    return (
        f"你是问题分析主Agent。当前第 {loop_round}/{max_rounds} 轮。\n"
        "请先给出一段简短会议发言(chat_message)，然后给出对各专家Agent的命令清单(commands)。\n"
        "同时你需要决定下一步调度：next_mode/next_agent；如果你判断证据充分可以停止，设置 should_stop=true 并给出 stop_reason。\n"
        "必须覆盖 LogAgent、DomainAgent、CodeAgent；若已存在历史结论，可补充 CriticAgent/RebuttalAgent/JudgeAgent 命令。\n"
        "命令要具体到分析重点，不要泛泛而谈。\n\n"
        f"故障上下文:\n```json\n{to_json(context)}\n```\n\n"
        f"{dialogue_block}"
        f"已有观点卡片:\n```json\n{to_json(peer_items)}\n```\n\n"
        f"仅输出 JSON，格式:\n```json\n{to_json(schema)}\n```"
    )


def build_problem_analysis_supervisor_prompt(
    *,
    loop_round: int,
    max_rounds: int,
    context: Dict[str, Any],
    round_history_cards: List[AgentEvidence],
    open_questions: List[str],
    discussion_step_count: int,
    max_discussion_steps: int,
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    recent_messages = [
        {
            "agent": card.agent_name,
            "phase": card.phase,
            "conclusion": card.conclusion[:160],
            "confidence": round(float(card.confidence or 0.0), 3),
        }
        for card in round_history_cards[-8:]
    ]
    schema = coordinator_command_schema()
    dialogue_block = ""
    if dialogue_items:
        dialogue_block = f"\n最近对话消息:\n```json\n{to_json(dialogue_items[-10:])}\n```\n"
    return (
        f"你是问题分析主Agent，正在主持故障分析讨论。当前第 {loop_round}/{max_rounds} 轮。\n"
        "请像会议主持人一样决定下一位发言者或停止讨论。你必须输出 JSON。\n"
        "规则：\n"
        "1) 优先让Agent回应他人观点而不是重复自己的完整分析；\n"
        "2) 若证据不足，继续调度某个专家发言并下达具体命令；\n"
        "3) 若你判断结论已充分，设置 should_stop=true；但若尚未形成裁决，next_agent 应为 JudgeAgent。\n"
        "4) commands 只需给本步计划执行的Agent（1-3个）下命令。\n\n"
        f"讨论步数预算: {discussion_step_count}/{max_discussion_steps}\n"
        f"故障上下文:\n```json\n{to_json(context)}\n```\n\n"
        f"{dialogue_block}"
        f"本轮最近发言:\n```json\n{to_json(recent_messages)}\n```\n\n"
        f"未决问题:\n```json\n{to_json(open_questions[:8])}\n```\n\n"
        f"输出 JSON 格式:\n```json\n{to_json(schema)}\n```"
    )


def build_agent_prompt(
    *,
    spec: AgentSpec,
    loop_round: int,
    max_rounds: int,
    max_history_items: int,
    context: Dict[str, Any],
    history_cards: List[AgentEvidence],
    assigned_command: Optional[Dict[str, Any]],
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    history_items = [
        {
            "agent": card.agent_name,
            "phase": card.phase,
            "summary": card.summary[:120],
            "conclusion": card.conclusion[:140],
            "evidence": card.evidence_chain[:2],
            "confidence": round(float(card.confidence), 3),
        }
        for card in history_cards[-max_history_items:]
    ]
    output_schema = judge_output_schema() if spec.name == "JudgeAgent" else _normal_output_schema()
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
        dialogue_block = f"最近对话消息：\n```json\n{to_json(dialogue_items[-8:])}\n```\n\n"
    return (
        f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段={spec.phase}。\n"
        "只需要基于核心观点与结论推理，不要复述全部历史，结论请简短。\n"
        "请以真人讨论口吻在 chat_message 中表达你的发言（1-3句），然后输出 JSON。\n\n"
        f"{output_constraints}"
        f"{command_block}"
        f"{dialogue_block}"
        f"故障上下文：\n```json\n{to_json(context)}\n```\n\n"
        f"最近结论卡片：\n```json\n{to_json(history_items)}\n```\n\n"
        f"请仅输出 JSON，格式示例：\n```json\n{to_json(output_schema)}\n```"
    )


def build_collaboration_prompt(
    *,
    spec: AgentSpec,
    loop_round: int,
    max_rounds: int,
    context: Dict[str, Any],
    peer_cards: List[AgentEvidence],
    assigned_command: Optional[Dict[str, Any]],
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    peer_items = [
        {
            "agent": card.agent_name,
            "summary": card.summary[:120],
            "conclusion": card.conclusion[:160],
            "confidence": round(float(card.confidence), 3),
        }
        for card in peer_cards
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
        dialogue_block = f"最近对话消息：\n```json\n{to_json(dialogue_items[-8:])}\n```\n\n"
    return (
        f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段=analysis。\n"
        "现在进入协同复核阶段：你必须基于其他 Agent 的结论进行交叉校验并修正自己的判断。\n"
        "请以真人讨论口吻在 chat_message 中明确你在回应谁、采纳或反驳什么。\n"
        "要求：\n"
        "1) 明确指出至少 1 条你采纳或反驳的同伴结论；\n"
        "2) 在 evidence_chain 中包含同伴观点依据（可写成 peer:<agent_name>:<观点>）；\n"
        "3) 仅输出 JSON，不要解释文本，保持精炼。\n\n"
        f"{command_block}"
        f"{dialogue_block}"
        f"故障上下文：\n```json\n{to_json(context)}\n```\n\n"
        f"同伴结论：\n```json\n{to_json(peer_items)}\n```\n\n"
        f"输出格式：\n```json\n{to_json(_normal_output_schema())}\n```"
    )


def build_peer_driven_prompt(
    *,
    spec: AgentSpec,
    loop_round: int,
    max_rounds: int,
    context: Dict[str, Any],
    peer_items: List[Dict[str, Any]],
    assigned_command: Optional[Dict[str, Any]],
    dialogue_items: Optional[List[Dict[str, Any]]] = None,
    to_json: ToJsonFn,
) -> str:
    dialogue_block = ""
    if dialogue_items:
        dialogue_block = f"最近对话消息：\n```json\n{to_json(dialogue_items[-10:])}\n```\n\n"
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
            f"{command_block}"
            f"{dialogue_block}"
            f"故障上下文：\n```json\n{to_json(context)}\n```\n\n"
            f"同伴结论：\n```json\n{to_json(peer_items)}\n```\n\n"
            f"输出格式：\n```json\n{to_json(judge_output_schema())}\n```"
        )

    command_block = ""
    if assigned_command:
        command_block = (
            f"\n主Agent命令：\n```json\n{to_json(assigned_command)}\n```\n"
            "你必须先在 chat_message 中确认收到主Agent命令，再给出执行结果。\n"
        )
    return (
        f"你是 {spec.name}（{spec.role}）。当前第 {loop_round}/{max_rounds} 轮，阶段={spec.phase}。\n"
        "必须基于其他 Agent 的结论进行分析，禁止独立分析。\n"
        "请以真人讨论口吻在 chat_message 中先说结论（1-3句），再给结构化字段。\n"
        "要求：\n"
        "1) 至少明确采纳/反驳 1 条同伴结论；\n"
        "2) evidence_chain 至少包含 1 条 peer:<agent_name>:<观点>；\n"
        "3) 仅输出 JSON，内容尽量简短。\n\n"
        f"{command_block}"
        f"{dialogue_block}"
        f"故障上下文：\n```json\n{to_json(context)}\n```\n\n"
        f"同伴结论：\n```json\n{to_json(peer_items)}\n```\n\n"
        f"输出格式：\n```json\n{to_json(_normal_output_schema())}\n```"
    )


def _normal_output_schema() -> Dict[str, Any]:
    return {
        "chat_message": "",
        "analysis": "",
        "conclusion": "",
        "evidence_chain": [""],
        "confidence": 0.0,
    }
