"""
Agent 节点工厂模块

本模块负责创建 LangGraph 图中的 Agent 执行节点和阶段处理节点。

设计原则：
- 节点直接执行图步骤，而非委托给编排器的包装方法
- 编排器仍拥有底层 LLM/事件/存储辅助方法
- 节点级别的状态转换在此定义

主要组件：
- execute_single_phase_agent: 执行单个 Agent 的核心逻辑
- build_agent_node: 创建 Agent 执行节点
- build_phase_handler_node: 创建阶段处理节点

Agent and phase node factories.

These nodes execute graph steps directly instead of delegating to wrapper methods
on the orchestrator. The orchestrator still owns low-level LLM/event/storage
helpers, but node-level state transitions are now defined here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from app.runtime.langgraph.mailbox import clone_mailbox, compact_mailbox, dequeue_messages, enqueue_message
from app.runtime.langgraph.state import DebateTurn, flatten_structured_state_view
from app.runtime.messages import AgentMessage


def _apply_step_result(orchestrator: Any, state: Dict[str, Any], result: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    应用步骤执行结果到状态

    将节点执行结果合并到图状态中。

    Args:
        orchestrator: 编排器实例
        state: 当前状态
        result: 执行结果

    Returns:
        Dict[str, Any]: 更新后的状态
    """
    return orchestrator._graph_apply_step_result(state, result)


async def execute_single_phase_agent(
    orchestrator: Any,
    *,
    agent_name: str,
    loop_round: int,
    compact_context: Dict[str, Any],
    history_cards: list[Any],
    agent_commands: Dict[str, Dict[str, Any]] | None = None,
    dialogue_items: list[Dict[str, Any]] | None = None,
    inbox_messages: list[Dict[str, Any]] | None = None,
    agent_mailbox: Dict[str, list[Dict[str, Any]]] | None = None,
    agent_local_state: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    执行单个阶段的 Agent

    这是 Agent 执行的核心函数，负责：
    1. 获取 Agent 规格配置
    2. 处理 Commander 下发的命令
    3. 构建 Agent 执行上下文
    4. 调用 LLM 执行 Agent
    5. 记录执行结果
    6. 发送消息到邮箱

    Args:
        orchestrator: 编排器实例
        agent_name: Agent 名称
        loop_round: 当前循环轮次
        compact_context: 压缩后的上下文
        history_cards: 历史卡片列表
        agent_commands: Agent 命令字典
        dialogue_items: 对话项列表
        inbox_messages: 收件箱消息
        agent_mailbox: Agent 邮箱

    Returns:
        Dict[str, Any]: 包含更新后邮箱的状态更新
    """
    # 获取 Agent 规格配置
    spec = orchestrator._spec_by_name(agent_name)
    if not spec:
        # Agent 不存在，返回空的邮箱更新
        return {"agent_mailbox": compact_mailbox(clone_mailbox(agent_mailbox or {}))}

    round_number = len(orchestrator.turns) + 1
    mailbox = clone_mailbox(agent_mailbox or {})
    assigned_command = (agent_commands or {}).get(agent_name)

    # 如果有命令，发出命令下发事件
    if assigned_command:
        await orchestrator._emit_agent_command_issued(
            commander="ProblemAnalysisAgent",
            target=agent_name,
            loop_round=loop_round,
            round_number=round_number,
            command=assigned_command,
        )

    # 构建 Agent 执行上下文（包含工具绑定信息）
    context_with_tools = await orchestrator._build_agent_context_with_tools(
        agent_name=agent_name,
        compact_context=compact_context,
        loop_round=loop_round,
        round_number=round_number,
        assigned_command=assigned_command,
    )
    # 把当前 Agent 的私有工作记忆挂到上下文里，只给自己后续轮次参考。
    context_with_tools = orchestrator._attach_agent_local_context(
        context_with_tools=context_with_tools,
        agent_name=agent_name,
        agent_local_state=agent_local_state,
    )

    # 应用工具开关到规格（根据上下文决定是否启用工具）
    effective_spec = orchestrator._apply_tool_switch_to_spec(
        spec=spec,
        context_with_tools=context_with_tools,
    )

    # 构建 Agent 提示（包含同侪信息、历史等）
    prompt = orchestrator._build_peer_driven_prompt(
        spec=effective_spec,
        loop_round=loop_round,
        context=context_with_tools,
        history_cards=history_cards,
        assigned_command=assigned_command,
        dialogue_items=dialogue_items,
        inbox_messages=inbox_messages,
    )

    # 特殊处理：快速模式下跳过 VerificationAgent
    if agent_name == "VerificationAgent" and not bool(
        getattr(orchestrator, "_require_verification_plan", True)
    ):
        now = datetime.utcnow()
        turn = DebateTurn(
            round_number=round_number,
            phase=effective_spec.phase,
            agent_name=effective_spec.name,
            agent_role=effective_spec.role,
            model={"name": "rule-skip"},
            input_message=prompt,
            output_content={
                "chat_message": "快速模式下跳过验证计划生成，直接进入结论落地。",
                "analysis": "当前会话策略为 quick/background，不强制补充 VerificationAgent 计划。",
                "conclusion": "已跳过验证计划生成，不影响根因与修复建议输出。",
                "confidence": 0.8,
                "evidence_chain": [],
            },
            confidence=0.8,
            started_at=now,
            completed_at=now,
        )
        await orchestrator._emit_event(
            {
                "type": "verification_skipped",
                "phase": "verification",
                "agent_name": "VerificationAgent",
                "loop_round": loop_round,
                "round_number": round_number,
                "reason": "runtime_policy_quick_mode",
            }
        )
    else:
        # 正常执行 Agent
        turn = await orchestrator._agent_runner.run_agent(
            spec=effective_spec,
            prompt=prompt,
            round_number=round_number,
            loop_round=loop_round,
            history_cards_context=history_cards,
            execution_context=context_with_tools,
        )

    # 记录执行回合
    await orchestrator._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
    updated_agent_local_state = orchestrator._build_agent_local_state_update(
        agent_name=agent_name,
        turn=turn,
        agent_local_state=agent_local_state,
    )

    # 如果有命令，发出命令反馈事件
    if assigned_command:
        await orchestrator._emit_agent_command_feedback(
            source=agent_name,
            loop_round=loop_round,
            round_number=round_number,
            command=assigned_command,
            turn=turn,
        )
        # 向 ProblemAnalysisAgent 发送反馈消息
        enqueue_message(
            mailbox,
            receiver="ProblemAnalysisAgent",
            message=AgentMessage(
                sender=agent_name,
                receiver="ProblemAnalysisAgent",
                message_type="feedback",
                content={
                    "command": str(assigned_command.get("task") or "")[:240],
                    "conclusion": str((turn.output_content or {}).get("conclusion") or "")[:240],
                    "confidence": float(turn.confidence or 0.0),
                },
            ),
        )

    # 向其他 Agent 广播证据消息
    conclusion = str((turn.output_content or {}).get("conclusion") or "")[:280]
    evidence = list((turn.output_content or {}).get("evidence_chain") or [])[:3]
    for receiver in orchestrator._evidence_recipients(
        sender=agent_name,
        turn=turn,
        assigned_command=assigned_command,
        context_with_tools=context_with_tools,
    ):
        if receiver == agent_name:
            continue
        enqueue_message(
            mailbox,
            receiver=receiver,
            message=AgentMessage(
                sender=agent_name,
                receiver=receiver,
                message_type="evidence",
                content={
                    "phase": turn.phase,
                    "conclusion": conclusion,
                    "evidence_chain": evidence,
                    "confidence": float(turn.confidence or 0.0),
                },
            ),
        )

    return {
        "agent_mailbox": compact_mailbox(mailbox),
        "agent_local_state": updated_agent_local_state,
    }


def build_agent_node(orchestrator: Any, agent_name: str) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """
    构建 Agent 执行节点

    创建一个异步节点函数，用于在 LangGraph 图中执行指定的 Agent。

    节点执行流程：
    1. 从状态中提取上下文信息
    2. 获取 Agent 的收件箱消息
    3. 调用 execute_single_phase_agent 执行 Agent
    4. 更新状态（历史卡片、邮箱、消息）
    5. 如果是 JudgeAgent，发出最终摘要事件

    Args:
        orchestrator: 编排器实例
        agent_name: Agent 名称

    Returns:
        Callable: 异步节点函数
    """
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        flat_state = flatten_structured_state_view(state or {})
        # 提取状态信息
        """执行node相关逻辑，并为当前模块提供可复用的处理能力。"""
        loop_round = int(flat_state.get("current_round") or 1)
        context_summary = flat_state.get("context_summary") or {}
        history_cards = orchestrator._history_cards_for_state(flat_state, limit=20)
        dialogue_items = orchestrator._dialogue_items_from_messages(
            list(flat_state.get("messages") or []),
            limit=6,
            char_budget=720,
        )

        # 获取收件箱消息
        mailbox = clone_mailbox(flat_state.get("agent_mailbox") or {})
        inbox_messages, mailbox = dequeue_messages(mailbox, receiver=agent_name)
        agent_local_state = dict(flat_state.get("agent_local_state") or {})

        # 构建压缩上下文
        compact_context = orchestrator._compact_round_context(context_summary)

        # 执行 Agent
        execution_result = await execute_single_phase_agent(
            orchestrator,
            agent_name=agent_name,
            loop_round=loop_round,
            compact_context=compact_context,
            history_cards=history_cards,
            agent_commands=dict(flat_state.get("agent_commands") or {}),
            dialogue_items=dialogue_items,
            inbox_messages=inbox_messages,
            agent_mailbox=mailbox,
            agent_local_state=agent_local_state,
        )

        mailbox = clone_mailbox(execution_result.get("agent_mailbox") or mailbox)
        agent_local_state = dict(execution_result.get("agent_local_state") or agent_local_state)

        # 如果是 JudgeAgent，发出问题分析最终摘要
        if agent_name == "JudgeAgent":
            await orchestrator._emit_problem_analysis_final_summary(
                loop_round=loop_round,
                history_cards=history_cards,
            )

        # 构建状态更新结果
        result: Dict[str, Any] = {
            "history_cards": history_cards,
            "agent_mailbox": compact_mailbox(mailbox),
            "agent_local_state": agent_local_state,
        }

        # 将最新卡片转换为 AI 消息，添加到状态
        if history_cards:
            latest_message = orchestrator._card_to_ai_message(history_cards[-1])
            if latest_message is not None:
                result["messages"] = [latest_message]

        return _apply_step_result(orchestrator, flat_state, result)

    return _node


def build_phase_handler_node(
    orchestrator: Any,
    handler_name: str,
) -> Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]:
    """
    构建阶段处理节点

    创建一个异步节点函数，用于执行编排器上的特定处理方法。
    主要用于并行分析和协作阶段。

    Args:
        orchestrator: 编排器实例
        handler_name: 处理方法名称（如 "_graph_analysis_parallel"）

    Returns:
        Callable: 异步节点函数
    """
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        # 获取并调用处理方法
        """执行node相关逻辑，并为当前模块提供可复用的处理能力。"""
        handler = getattr(orchestrator, handler_name)
        result = await handler(state)
        return _apply_step_result(orchestrator, state, result)

    return _node
