"""
Supervisor 节点执行模块。

这个文件负责把一次 supervisor 决策真正落成图状态增量：
- 调用 routing strategy 得到 route_decision
- 处理人审暂停和 doom loop guard
- 写 supervisor 事件
- 把新增命令写回 mailbox
"""

from __future__ import annotations

from typing import Any, Dict

from app.runtime.langgraph.mailbox import clone_mailbox, compact_mailbox, enqueue_message
from app.runtime.langgraph.state import structured_state_snapshot
from app.runtime.messages import AgentMessage


async def execute_supervisor_decide(orchestrator: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行一次 supervisor 决策，并把结果转换成可并回图状态的增量。

    它不会直接执行 Agent，只负责决定下一跳、记录理由，并把新增命令写回 mailbox。
    """
    history_cards = orchestrator._history_cards_for_state(state, limit=20)
    dialogue_items = orchestrator._dialogue_items_from_messages(
        list(state.get("messages") or []),
        limit=6,
        char_budget=720,
    )
    loop_round = int(state.get("current_round") or 1)
    discussion_step_count = int(state.get("discussion_step_count") or 0)
    max_discussion_steps = int(state.get("max_discussion_steps") or orchestrator.MAX_DISCUSSION_STEPS_PER_ROUND)
    round_cards = orchestrator._round_cards_for_routing(state)
    preseed_step = str(state.get("next_step") or "").strip()
    supervisor_stop_requested = bool(state.get("supervisor_stop_requested") or False)
    supervisor_stop_reason = str(state.get("supervisor_stop_reason") or "").strip()

    # routing strategy 只负责给出 route_decision，本函数再把它落成实际状态更新。
    routing_result = await orchestrator._routing_strategy.decide(
        orchestrator=orchestrator,
        state=state,
        history_cards=history_cards,
        round_cards=round_cards,
        dialogue_items=dialogue_items,
        loop_round=loop_round,
        discussion_step_count=discussion_step_count,
        max_discussion_steps=max_discussion_steps,
        preseed_step=preseed_step,
        supervisor_stop_requested=supervisor_stop_requested,
        supervisor_stop_reason=supervisor_stop_reason,
    )
    route_decision = dict(routing_result.decision or {})
    mode = str(routing_result.mode or "langgraph_supervisor_dynamic")
    deployment_profile = state.get("context", {}).get("deployment_profile") if isinstance(state.get("context"), dict) else {}
    deployment_name = (
        str(deployment_profile.get("name") or "").strip()
        if isinstance(deployment_profile, dict)
        else ""
    )
    # 人工审核只在 governed deployment 下允许生效，避免普通模式误触发暂停态。
    should_pause_for_review = bool(route_decision.get("should_pause_for_review") or False) and deployment_name == "production_governed"
    review_reason = str(route_decision.get("review_reason") or "").strip()
    review_payload = route_decision.get("review_payload") if isinstance(route_decision.get("review_payload"), dict) else {}
    resume_from_step = str(route_decision.get("resume_from_step") or "report_generation").strip()

    # 重新派生一次会话聚合状态，让决策说明里能带上 open_questions/claims 统计。
    convo_state = orchestrator._derive_conversation_state_with_context(
        history_cards,
        messages=list(state.get("messages") or []),
        existing_agent_outputs=dict(state.get("agent_outputs") or {}),
    )
    next_step = str(route_decision.get("next_step") or "").strip()
    # 如果 supervisor 连续几步都在重复同一类非 Judge 路由，就触发 doom loop guard 强制收敛。
    existing_notes = list(state.get("supervisor_notes") or [])
    recent_steps = [str((item or {}).get("next_step") or "").strip() for item in existing_notes[-3:]]
    if orchestrator._doom_loop_guard.should_force(next_step, recent_steps):
        route_decision["next_step"] = orchestrator._doom_loop_guard.forced_step
        route_decision["should_stop"] = False
        route_decision["stop_reason"] = ""
        reason = str(route_decision.get("reason") or "").strip()
        route_decision["reason"] = f"{reason}；检测到重复调度，强制切换JudgeAgent收敛".strip("；")
        next_step = orchestrator._doom_loop_guard.forced_step
    note = {
        "loop_round": loop_round,
        "discussion_step_count": discussion_step_count,
        "max_discussion_steps": max_discussion_steps,
        "next_step": next_step,
        "open_questions_count": len(convo_state.get("open_questions") or []),
        "claims_count": len(convo_state.get("claims") or []),
        "reason": str(route_decision.get("reason") or ""),
        "should_stop": bool(route_decision.get("should_stop") or False),
        "stop_reason": str(route_decision.get("stop_reason") or ""),
        "awaiting_human_review": should_pause_for_review,
        "human_review_reason": review_reason,
    }
    # 决策事件必须先发出去，前端链路图和回放页才能解释“为什么会走到下一步”。
    await orchestrator._emit_event(
        {
            "type": "supervisor_decision",
            "session_id": orchestrator.session_id,
            "loop_round": loop_round,
            "discussion_step_count": discussion_step_count,
            "max_discussion_steps": max_discussion_steps,
            "next_step": next_step or None,
            "reason": str(route_decision.get("reason") or ""),
            "mode": mode,
            "should_stop": bool(route_decision.get("should_stop") or False),
            "stop_reason": str(route_decision.get("stop_reason") or "")[:240],
            "should_pause_for_review": should_pause_for_review,
            "review_reason": review_reason[:240],
            "open_questions_count": note["open_questions_count"],
            "claims_count": note["claims_count"],
        }
    )
    notes = existing_notes
    notes.append(note)
    result: Dict[str, Any] = {
        "history_cards": history_cards,
        "next_step": next_step,
        "supervisor_stop_requested": bool(route_decision.get("should_stop") or False),
        "supervisor_stop_reason": str(route_decision.get("stop_reason") or ""),
        "supervisor_notes": notes[-20:],
        "awaiting_human_review": should_pause_for_review,
        "human_review_reason": review_reason,
        "human_review_payload": review_payload,
        "resume_from_step": resume_from_step if should_pause_for_review else "",
        **convo_state,
    }
    mailbox = clone_mailbox(state.get("agent_mailbox") or {})
    if "agent_commands" in route_decision:
        commands = dict(route_decision.get("agent_commands") or {})
        result["agent_commands"] = commands
        # supervisor 如果在这一步追加了新命令，要同步写回 mailbox，供后续专家节点消费。
        for target, command in commands.items():
            if not isinstance(command, dict):
                continue
            enqueue_message(
                mailbox,
                receiver=target,
                message=AgentMessage(
                    sender="ProblemAnalysisAgent",
                    receiver=str(target),
                    message_type="command",
                    content={
                        "task": str(command.get("task") or "").strip(),
                        "focus": str(command.get("focus") or "").strip(),
                        "expected_output": str(command.get("expected_output") or "").strip(),
                    },
                ),
            )
    result["agent_mailbox"] = compact_mailbox(mailbox)
    # 返回前补一份 structured snapshot，保证后续节点拿到的是一致的状态视图。
    merged_preview = {**dict(state), **result}
    return {**result, **structured_state_snapshot(merged_preview)}
