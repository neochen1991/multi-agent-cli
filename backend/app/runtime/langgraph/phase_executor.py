"""
多 Agent 阶段执行器。

这个模块专门负责“某一整个阶段怎么跑”，例如：
- analysis 阶段的并行分析
- collaboration 阶段的协作补充

之所以单独拆出来，是为了把 orchestrator 主类从大段批处理逻辑中解耦出来。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.runtime.langgraph.mailbox import compact_mailbox, dequeue_messages, enqueue_message
from app.runtime.langgraph.state import AgentSpec
from app.runtime.messages import AgentEvidence, AgentMessage

logger = structlog.get_logger()


class PhaseExecutor:
    """承接阶段级重执行逻辑，避免 orchestrator 主类持续膨胀。"""

    def __init__(self, orchestrator: Any) -> None:
        """初始化当前对象，并准备后续执行所需的内部状态与依赖。"""
        self._orchestrator = orchestrator

    @staticmethod
    def _analysis_batches(target_names: List[str], priority_batches: List[List[str]], batch_limit: int) -> List[List[str]]:
        """
        按优先级和批次上限切分 Agent 列表。

        关键点：
        - priority_batches 决定谁先跑
        - batch_limit 决定单批次最多并发多少 Agent
        - remaining 会接住未命中优先组的 Agent，保证没人被漏掉
        """
        remaining = list(target_names)
        batches: List[List[str]] = []
        limit = max(1, int(batch_limit or 1))
        for group in priority_batches:
            selected = [name for name in remaining if name in set(group)]
            if selected:
                for index in range(0, len(selected), limit):
                    batches.append(selected[index:index + limit])
                remaining = [name for name in remaining if name not in set(selected)]
        if remaining:
            for index in range(0, len(remaining), limit):
                batches.append(remaining[index:index + limit])
        return batches

    async def run_parallel_analysis_phase(
        self,
        *,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        agent_commands: Optional[Dict[str, Dict[str, Any]]] = None,
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        agent_mailbox: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        """
        执行 analysis 阶段的并行分析波次。

        这里串起的流程是：
        1. 选择目标 analysis Agent
        2. 发出 command 事件
        3. 构建工具上下文和 prompt
        4. 按 batch 分批执行
        5. fan-in 汇总结果并回写 mailbox
        """
        orchestrator = self._orchestrator
        # 先锁定当前图配置下真正属于 analysis 阶段的 Agent。
        analysis_specs = {spec.name: spec for spec in orchestrator._agent_sequence() if spec.phase == "analysis"}
        if not analysis_specs:
            return
        allowed_targets = [
            name for name in orchestrator.PARALLEL_ANALYSIS_AGENTS if name in analysis_specs
        ]
        # 如果主 Agent 已显式点名，就优先执行这些目标；否则退回 profile 里的默认 Agent 集合。
        commanded_targets = [
            name for name in dict(agent_commands or {}).keys() if name in set(allowed_targets)
        ]
        target_names = commanded_targets or allowed_targets
        parallel_specs = [analysis_specs[name] for name in target_names]
        if not parallel_specs:
            return
        mailbox = agent_mailbox if agent_mailbox is not None else {}
        round_cursor = len(orchestrator.turns) + 1
        parallel_history = list(history_cards)
        # round_plans 保存“准备执行但尚未真正调用 LLM”的计划项，
        # 后面的批次调度只消费这份稳定计划表。
        round_plans: List[Dict[str, Any]] = []
        for spec in parallel_specs:
            round_number = round_cursor
            round_cursor += 1
            inbox_messages, mailbox = dequeue_messages(mailbox, receiver=spec.name)
            assigned_command = (agent_commands or {}).get(spec.name)
            round_plans.append(
                {
                    "spec": spec,
                    "round_number": round_number,
                    "assigned_command": assigned_command or {},
                    "inbox_messages": inbox_messages,
                }
            )

        # 阶段开始事件先发出去，前端才能知道“并行分析已启动”。
        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_started",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "agents": [str(item["spec"].name) for item in round_plans],
            }
        )
        for item in round_plans:
            spec = item["spec"]
            round_number = int(item["round_number"])
            assigned_command = dict(item["assigned_command"] or {})
            # 命令事件必须先于 Agent 真正执行，满足“命令先行”的审计要求。
            if assigned_command:
                await orchestrator._emit_agent_command_issued(
                    commander="ProblemAnalysisAgent",
                    target=spec.name,
                    loop_round=loop_round,
                    round_number=round_number,
                    command=assigned_command,
                )

        # 这里才为每个 Agent 组装实际执行输入：工具上下文、effective spec 和 prompt。
        parallel_inputs: List[Dict[str, Any]] = []
        for item in round_plans:
            spec = item["spec"]
            round_number = int(item["round_number"])
            assigned_command = dict(item["assigned_command"] or {})
            inbox_messages = list(item["inbox_messages"] or [])
            # 每个 Agent 的 prompt 都依赖各自的工具上下文和责任田线索，不能复用同一份。
            context_with_tools = await orchestrator._build_agent_context_with_tools(
                agent_name=spec.name,
                compact_context=compact_context,
                loop_round=loop_round,
                round_number=round_number,
                assigned_command=assigned_command,
            )
            effective_spec = orchestrator._apply_tool_switch_to_spec(
                spec=spec,
                context_with_tools=context_with_tools,
            )
            prompt = orchestrator._build_agent_prompt(
                spec=effective_spec,
                loop_round=loop_round,
                context=context_with_tools,
                history_cards=parallel_history,
                assigned_command=assigned_command,
                dialogue_items=dialogue_items,
                inbox_messages=inbox_messages,
            )
            parallel_inputs.append(
                {
                    "spec": effective_spec,
                    "round_number": round_number,
                    "prompt": prompt,
                    "assigned_command": assigned_command,
                    "inbox_messages": inbox_messages,
                    "context_with_tools": context_with_tools,
                }
            )

        parallel_start_time = datetime.utcnow()
        logger.info(
            "parallel_analysis_executing",
            session_id=orchestrator.session_id,
            loop_round=loop_round,
            agents=[str(item["spec"].name) for item in parallel_inputs],
        )

        # priority_batches 决定关键证据 Agent 的优先级，batch_limit 决定单批最大并发。
        priority_batches = [list(batch) for batch in getattr(orchestrator, "ANALYSIS_PRIORITY_BATCHES", ())]
        batch_limit = int(orchestrator._analysis_batch_limit(collaboration=False))
        batch_names = self._analysis_batches(
            [str(item["spec"].name) for item in parallel_inputs],
            priority_batches,
            batch_limit,
        )
        result_map: Dict[str, Any] = {}
        # 逐批执行，避免一次 fan-out 把 LLM 并发槽位完全占满。
        for batch_index, names in enumerate(batch_names, start=1):
            batch_inputs = [item for item in parallel_inputs if str(item["spec"].name) in set(names)]
            await orchestrator._emit_event(
                {
                    "type": "parallel_analysis_batch_started",
                    "phase": "analysis",
                    "loop_round": loop_round,
                    "session_id": orchestrator.session_id,
                    "batch_index": batch_index,
                    "batch_total": len(batch_names),
                    "agents": names,
                }
            )
            # 同一批内允许并发，但批次之间必须串行，避免一次 fan-out 占满全部 LLM 槽位。
            parallel_tasks = [
                asyncio.create_task(
                    orchestrator._agent_runner.run_agent(
                        spec=item["spec"],
                        prompt=item["prompt"],
                        round_number=int(item["round_number"]),
                        loop_round=loop_round,
                        history_cards_context=history_cards,
                    )
                )
                for item in batch_inputs
            ]
            batch_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
            await orchestrator._emit_event(
                {
                    "type": "parallel_analysis_batch_completed",
                    "phase": "analysis",
                    "loop_round": loop_round,
                    "session_id": orchestrator.session_id,
                    "batch_index": batch_index,
                    "batch_total": len(batch_names),
                    "agents": names,
                }
            )
            for item, result in zip(batch_inputs, batch_results):
                result_map[str(item["spec"].name)] = result

        parallel_duration = (datetime.utcnow() - parallel_start_time).total_seconds()
        logger.info(
            "parallel_analysis_completed_duration",
            session_id=orchestrator.session_id,
            loop_round=loop_round,
            duration_seconds=parallel_duration,
            agents_count=len(parallel_inputs),
        )

        success_count = 0
        error_count = 0
        degraded_count = 0
        # fan-in 阶段负责把各专家 turn 重新折回事件流、mailbox 和主 Agent 反馈中。
        fan_in_items: List[Dict[str, Any]] = []
        for item in parallel_inputs:
            spec = item["spec"]
            round_number = int(item["round_number"])
            prompt = str(item["prompt"])
            assigned_command = dict(item["assigned_command"] or {})
            context_with_tools = item.get("context_with_tools") if isinstance(item.get("context_with_tools"), dict) else {}
            result = result_map.get(spec.name)
            # 无论成功还是失败，都必须生成一个可记录的 turn，保证轨迹闭环。
            if isinstance(result, Exception):
                error_count += 1
                error_text = str(result).strip() or result.__class__.__name__
                logger.error(
                    "parallel_agent_failed",
                    session_id=orchestrator.session_id,
                    agent=spec.name,
                    loop_round=loop_round,
                    error=error_text,
                )
                turn = await orchestrator._create_fallback_turn(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    error_text=error_text,
                )
            else:
                success_count += 1
                turn = result
            # 工具不可用时，统一转成“受限分析”语义，而不是丢掉本轮 LLM 分析结果。
            turn = orchestrator._apply_tool_limited_semantics(
                turn=turn,
                spec=spec,
                assigned_command=assigned_command,
                context_with_tools=context_with_tools,
            )
            if bool((turn.output_content or {}).get("degraded")):
                degraded_count += 1
            await orchestrator._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
            fan_in_items.append(
                {
                    "agent_name": spec.name,
                    "phase": turn.phase,
                    "confidence": float(turn.confidence or 0.0),
                    "conclusion": str((turn.output_content or {}).get("conclusion") or "")[:220],
                    "status": "error" if isinstance(result, Exception) else "ok",
                    "degraded": bool((turn.output_content or {}).get("degraded")),
                    "evidence_status": str((turn.output_content or {}).get("evidence_status") or ""),
                    "tool_status": str((turn.output_content or {}).get("tool_status") or ""),
                }
            )
            if assigned_command:
                await orchestrator._emit_agent_command_feedback(
                    source=spec.name,
                    loop_round=loop_round,
                    round_number=round_number,
                    command=assigned_command,
                    turn=turn,
                )
                enqueue_message(
                    mailbox,
                    receiver="ProblemAnalysisAgent",
                    message=AgentMessage(
                        sender=spec.name,
                        receiver="ProblemAnalysisAgent",
                        message_type="feedback",
                        content={
                            "command": str(assigned_command.get("task") or "")[:240],
                            "conclusion": str((turn.output_content or {}).get("conclusion") or "")[:240],
                            "confidence": float(turn.confidence or 0.0),
                        },
                    ),
                )
            conclusion = str((turn.output_content or {}).get("conclusion") or "")[:280]
            evidence = list((turn.output_content or {}).get("evidence_chain") or [])[:3]
            for receiver in ["ProblemAnalysisAgent", *target_names]:
                if receiver == spec.name:
                    continue
                enqueue_message(
                    mailbox,
                    receiver=receiver,
                    message=AgentMessage(
                        sender=spec.name,
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

        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_completed",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "agents": [str(item["spec"].name) for item in parallel_inputs],
                "success_count": success_count,
                "error_count": error_count,
                "degraded_count": degraded_count,
                "duration_seconds": parallel_duration,
            }
        )
        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_fan_in_completed",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "items": fan_in_items,
            }
        )
        if agent_mailbox is not None:
            agent_mailbox.clear()
            agent_mailbox.update(compact_mailbox(mailbox))

    async def run_collaboration_phase(
        self,
        *,
        loop_round: int,
        compact_context: Dict[str, Any],
        history_cards: List[AgentEvidence],
        dialogue_items: Optional[List[Dict[str, Any]]] = None,
        agent_mailbox: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        """
        执行 analysis 后的协作阶段。

        协作阶段不是重新做一轮完整分析，而是让专家 Agent 基于同伴结论做补充、校验或收敛。
        因此这里会读取 peer_cards，并构造 collaboration prompt。
        """
        orchestrator = self._orchestrator
        parallel_specs = [
            spec
            for spec in orchestrator._agent_sequence()
            if spec.phase == "analysis" and spec.name in set(orchestrator.PARALLEL_ANALYSIS_AGENTS)
        ]
        if not parallel_specs:
            return
        mailbox = agent_mailbox if agent_mailbox is not None else {}
        # 协作阶段只围绕“本轮已有结论”的专家展开，不重新拉起一整轮分析。
        peer_cards = orchestrator._latest_cards_for_agents(
            history_cards=history_cards,
            agent_names=[spec.name for spec in parallel_specs],
            limit=orchestrator.COLLABORATION_PEER_LIMIT,
        )
        round_cursor = len(orchestrator.turns) + 1
        collab_inputs: List[tuple[AgentSpec, int, str, List[Dict[str, Any]]]] = []
        for spec in parallel_specs:
            round_number = round_cursor
            round_cursor += 1
            inbox_messages, mailbox = dequeue_messages(mailbox, receiver=spec.name)
            context_with_tools = await orchestrator._build_agent_context_with_tools(
                agent_name=spec.name,
                compact_context=compact_context,
                loop_round=loop_round,
                round_number=round_number,
                assigned_command=None,
            )
            effective_spec = orchestrator._apply_tool_switch_to_spec(
                spec=spec,
                context_with_tools=context_with_tools,
            )
            prompt = orchestrator._build_collaboration_prompt(
                spec=effective_spec,
                loop_round=loop_round,
                context=context_with_tools,
                peer_cards=peer_cards,
                dialogue_items=dialogue_items,
                inbox_messages=inbox_messages,
            )
            collab_inputs.append((effective_spec, round_number, prompt, inbox_messages))

        # 协作阶段也要成组发事件，方便前端区分“第一次分析”和“二次协作”。
        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_collaboration_started",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "agents": [spec.name for spec, _, _, _ in collab_inputs],
            }
        )

        collab_start_time = datetime.utcnow()
        logger.info(
            "collaboration_phase_executing",
            session_id=orchestrator.session_id,
            loop_round=loop_round,
            agents=[spec.name for spec, _, _, _ in collab_inputs],
        )

        priority_batches = [list(batch) for batch in getattr(orchestrator, "ANALYSIS_PRIORITY_BATCHES", ())]
        # 协作阶段比 analysis 更克制，默认批次更小，优先保障收口链路。
        batch_limit = int(orchestrator._analysis_batch_limit(collaboration=True))
        batch_names = self._analysis_batches(
            [spec.name for spec, _, _, _ in collab_inputs],
            priority_batches,
            batch_limit,
        )
        collab_result_map: Dict[str, Any] = {}
        # 协作阶段同样使用批次控制，避免分析刚结束又把收口链路挤出队列。
        for batch_index, names in enumerate(batch_names, start=1):
            batch_inputs = [item for item in collab_inputs if item[0].name in set(names)]
            await orchestrator._emit_event(
                {
                    "type": "parallel_analysis_collaboration_batch_started",
                    "phase": "analysis",
                    "loop_round": loop_round,
                    "session_id": orchestrator.session_id,
                    "batch_index": batch_index,
                    "batch_total": len(batch_names),
                    "agents": names,
                }
            )
            collab_tasks = [
                asyncio.create_task(
                    orchestrator._agent_runner.run_agent(
                        spec=spec,
                        prompt=prompt,
                        round_number=round_number,
                        loop_round=loop_round,
                        history_cards_context=history_cards,
                    )
                )
                for spec, round_number, prompt, _ in batch_inputs
            ]
            batch_results = await asyncio.gather(*collab_tasks, return_exceptions=True)
            await orchestrator._emit_event(
                {
                    "type": "parallel_analysis_collaboration_batch_completed",
                    "phase": "analysis",
                    "loop_round": loop_round,
                    "session_id": orchestrator.session_id,
                    "batch_index": batch_index,
                    "batch_total": len(batch_names),
                    "agents": names,
                }
            )
            for item, result in zip(batch_inputs, batch_results):
                collab_result_map[item[0].name] = result

        collab_duration = (datetime.utcnow() - collab_start_time).total_seconds()
        logger.info(
            "collaboration_phase_completed_duration",
            session_id=orchestrator.session_id,
            loop_round=loop_round,
            duration_seconds=collab_duration,
            agents_count=len(collab_inputs),
        )

        success_count = 0
        error_count = 0
        for spec, round_number, prompt, _ in collab_inputs:
            result = collab_result_map.get(spec.name)
            if isinstance(result, Exception):
                error_count += 1
                error_text = str(result).strip() or result.__class__.__name__
                logger.error(
                    "collaboration_agent_failed",
                    session_id=orchestrator.session_id,
                    agent=spec.name,
                    loop_round=loop_round,
                    error=error_text,
                )
                turn = await orchestrator._create_fallback_turn(
                    spec=spec,
                    prompt=prompt,
                    round_number=round_number,
                    loop_round=loop_round,
                    error_text=error_text,
                )
            else:
                success_count += 1
                turn = result
            await orchestrator._record_turn(turn=turn, loop_round=loop_round, history_cards=history_cards)
            conclusion = str((turn.output_content or {}).get("conclusion") or "")[:280]
            evidence = list((turn.output_content or {}).get("evidence_chain") or [])[:3]
            for receiver in ["ProblemAnalysisAgent", *list(orchestrator.PARALLEL_ANALYSIS_AGENTS)]:
                if receiver == spec.name:
                    continue
                enqueue_message(
                    mailbox,
                    receiver=receiver,
                    message=AgentMessage(
                        sender=spec.name,
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

        await orchestrator._emit_event(
            {
                "type": "parallel_analysis_collaboration_completed",
                "phase": "analysis",
                "loop_round": loop_round,
                "session_id": orchestrator.session_id,
                "agents": [spec.name for spec, _, _, _ in collab_inputs],
                "success_count": success_count,
                "error_count": error_count,
                "duration_seconds": collab_duration,
            }
        )
        if agent_mailbox is not None:
            agent_mailbox.clear()
            agent_mailbox.update(compact_mailbox(mailbox))


__all__ = ["PhaseExecutor"]
