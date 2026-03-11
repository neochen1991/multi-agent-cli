"""test运行时消息flow相关测试。"""

import asyncio
from typing import Any, Dict, List

import pytest
from langchain_core.messages import AIMessage

import app.runtime.langgraph.execution as execution_module
from app.config import settings
from app.runtime.langgraph.execution import AgentInvokeResult, call_agent
from app.runtime.langgraph.output_truncation import get_output_reference
from app.runtime.langgraph.phase_executor import PhaseExecutor
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.langgraph.state import AgentSpec, DebateTurn, flatten_structured_state_view
from app.runtime.messages import AgentEvidence


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    """为测试场景提供orchestrator辅助逻辑。"""
    
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


@pytest.mark.asyncio
async def test_run_parallel_analysis_phase_passes_agent_local_state():
    """验证并行分析阶段会把私有上下文透传给阶段执行器。"""

    orchestrator = _orchestrator()
    captured: Dict[str, Any] = {}

    class _FakePhaseExecutor:
        async def run_parallel_analysis_phase(self, **kwargs: Any) -> None:
            # 这里直接记录 orchestrator 下传的参数，锁住 `agent_local_state`
            # 不能在阶段边界被意外丢失。
            captured.update(kwargs)

    orchestrator._phase_executor = _FakePhaseExecutor()
    local_state = {"CodeAgent": {"latest_conclusion": "事务边界过长"}}

    await orchestrator._run_parallel_analysis_phase(
        loop_round=1,
        compact_context={"service_name": "order-service"},
        history_cards=[],
        agent_commands={"CodeAgent": {"task": "检查事务边界"}},
        dialogue_items=[],
        agent_mailbox={},
        agent_local_state=local_state,
    )

    assert captured["agent_local_state"] == local_state


@pytest.mark.asyncio
async def test_run_collaboration_phase_passes_agent_local_state():
    """验证协作阶段也会透传私有上下文，避免后续阶段再次崩溃。"""

    orchestrator = _orchestrator()
    captured: Dict[str, Any] = {}

    class _FakePhaseExecutor:
        async def run_collaboration_phase(self, **kwargs: Any) -> None:
            # 这里覆盖协作阶段的透传路径，防止 parallel 修好后 collaboration 再炸。
            captured.update(kwargs)

    orchestrator._phase_executor = _FakePhaseExecutor()
    local_state = {"DatabaseAgent": {"open_questions": ["锁等待是否只是放大器"]}}

    await orchestrator._run_collaboration_phase(
        loop_round=1,
        compact_context={"service_name": "order-service"},
        history_cards=[],
        dialogue_items=[],
        agent_mailbox={},
        agent_local_state=local_state,
    )

    assert captured["agent_local_state"] == local_state


@pytest.mark.asyncio
async def test_graph_analysis_collaboration_skips_for_quick_mode_when_coverage_is_ready():
    """验证 quick 模式下关键证据已收敛时会跳过协作阶段。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "quick"
    orchestrator._enable_collaboration = True
    captured_events: List[Dict[str, Any]] = []

    class _FakePhaseExecutor:
        async def run_collaboration_phase(self, **kwargs: Any) -> None:
            raise AssertionError("quick 模式已满足收敛条件时，不应再进入 collaboration")

    async def _fake_emit_event(payload: Dict[str, Any]) -> None:
        captured_events.append(payload)

    orchestrator._phase_executor = _FakePhaseExecutor()
    orchestrator._emit_event = _fake_emit_event  # type: ignore[method-assign]

    state = {
        "current_round": 1,
        "context_summary": {"service_name": "order-service"},
        "history_cards": [
            AgentEvidence(
                agent_name="LogAgent",
                phase="analysis",
                summary="日志链路确认长事务",
                conclusion="事务内远程调用导致连接持有过长",
                evidence_chain=["log1", "log2"],
                confidence=0.74,
                raw_output={
                    "conclusion": "事务内远程调用导致连接持有过长",
                    "evidence_chain": ["log1", "log2"],
                    "confidence": 0.74,
                    "evidence_status": "context_grounded_without_tool",
                },
            ),
            AgentEvidence(
                agent_name="CodeAgent",
                phase="analysis",
                summary="代码差异确认事务边界扩大",
                conclusion="@Transactional 包裹了 promotionClient.checkQuota",
                evidence_chain=["code1", "code2"],
                confidence=0.76,
                raw_output={
                    "conclusion": "@Transactional 包裹了 promotionClient.checkQuota",
                    "evidence_chain": ["code1", "code2"],
                    "confidence": 0.76,
                    "evidence_status": "context_grounded_without_tool",
                },
            ),
            AgentEvidence(
                agent_name="DatabaseAgent",
                phase="analysis",
                summary="数据库是放大器而非根因",
                conclusion="锁等待由长事务放大，不是独立根因",
                evidence_chain=["db1", "db2"],
                confidence=0.72,
                raw_output={
                    "conclusion": "锁等待由长事务放大，不是独立根因",
                    "evidence_chain": ["db1", "db2"],
                    "confidence": 0.72,
                    "evidence_status": "context_grounded_without_tool",
                },
            ),
        ],
        "messages": [],
        "agent_mailbox": {},
        "agent_local_state": {},
    }

    result = await orchestrator._graph_analysis_collaboration(state)

    assert result["history_cards"] == state["history_cards"]
    assert any(item.get("type") == "parallel_analysis_collaboration_skipped" for item in captured_events)


@pytest.mark.asyncio
async def test_graph_analysis_collaboration_runs_when_quick_mode_coverage_is_not_ready():
    """验证 quick 模式下若关键证据未收敛，仍然会执行协作阶段。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "quick"
    orchestrator._enable_collaboration = True
    captured: Dict[str, Any] = {}

    class _FakePhaseExecutor:
        async def run_collaboration_phase(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    orchestrator._phase_executor = _FakePhaseExecutor()

    state = {
        "current_round": 1,
        "context_summary": {"service_name": "order-service"},
        "history_cards": [
            AgentEvidence(
                agent_name="LogAgent",
                phase="analysis",
                summary="只有日志侧先形成结论",
                conclusion="初步怀疑事务内远程调用",
                evidence_chain=["log1"],
                confidence=0.68,
                raw_output={
                    "conclusion": "初步怀疑事务内远程调用",
                    "evidence_chain": ["log1"],
                    "confidence": 0.68,
                    "evidence_status": "context_grounded_without_tool",
                },
            ),
            AgentEvidence(
                agent_name="CodeAgent",
                phase="analysis",
                summary="代码侧仍待补证",
                conclusion="需要确认 @Transactional 位置",
                evidence_chain=[],
                confidence=0.52,
                raw_output={
                    "conclusion": "需要确认 @Transactional 位置",
                    "confidence": 0.52,
                    "evidence_status": "inferred_without_tool",
                    "degraded": True,
                },
            ),
        ],
        "messages": [],
        "agent_mailbox": {},
        "agent_local_state": {"CodeAgent": {"open_questions": ["确认事务注解位置"]}},
    }

    result = await orchestrator._graph_analysis_collaboration(state)

    assert captured["loop_round"] == 1
    assert captured["agent_local_state"] == state["agent_local_state"]
    assert result["agent_local_state"] == state["agent_local_state"]


def test_dedupe_new_messages_skips_same_signature():
    """验证dedupe新增消息skips相同signature。"""
    
    orchestrator = _orchestrator()
    existing = [AIMessage(content="同意：先看日志证据", name="DomainAgent")]
    incoming = [AIMessage(content="同意：先看日志证据", name="DomainAgent")]

    deduped = orchestrator._dedupe_new_messages(existing_messages=existing, new_messages=incoming)

    assert deduped == []


def test_build_peer_driven_prompt_prefers_dialogue_items():
    """验证buildpeerdrivenPromptprefersdialogueitems。"""
    
    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="LogAgent",
        role="日志分析专家",
        phase="analysis",
        system_prompt="test",
    )
    prompt = orchestrator._build_peer_driven_prompt(
        spec=spec,
        loop_round=1,
        context={"service": "order-service"},
        history_cards=[],
        assigned_command=None,
        dialogue_items=[
            {
                "speaker": "DomainAgent",
                "phase": "analysis",
                "conclusion": "订单聚合根下游库存校验重试导致队列积压",
                "message": "我怀疑是库存校验重试策略导致请求堆积。",
            }
        ],
        inbox_messages=[
            {
                "sender": "ProblemAnalysisAgent",
                "receiver": "LogAgent",
                "message_type": "command",
                "content": {"task": "重点分析连接池耗尽"},
            }
        ],
    )

    assert "DomainAgent" in prompt
    assert "库存校验重试" in prompt
    assert "你收到的消息" in prompt
    assert "连接池耗尽" in prompt


def test_commander_prompt_prefers_dialogue_items_for_peer_summary():
    """验证主AgentPromptprefersdialogueitemsforpeer摘要。"""
    
    orchestrator = _orchestrator()
    prompt = orchestrator._build_problem_analysis_commander_prompt(
        loop_round=1,
        context={"service": "order-service"},
        history_cards=[
            AgentEvidence(
                agent_name="CodeAgent",
                phase="analysis",
                summary="旧结论",
                conclusion="历史结论：数据库慢查询",
                evidence_chain=[],
                confidence=0.6,
                raw_output={},
            )
        ],
        dialogue_items=[
            {
                "speaker": "LogAgent",
                "phase": "analysis",
                "conclusion": "最新结论：线程池饱和导致请求排队",
                "message": "我看到线程池队列持续增长。",
            }
        ],
    )

    assert "LogAgent" in prompt
    assert "线程池饱和" in prompt


def test_supervisor_prompt_uses_dialogue_recent_messages():
    """验证监督者Prompt使用dialogue最近消息。"""
    
    orchestrator = _orchestrator()
    prompt = orchestrator._build_problem_analysis_supervisor_prompt(
        loop_round=1,
        context={"service": "order-service"},
        history_cards=[],
        round_history_cards=[
            AgentEvidence(
                agent_name="DomainAgent",
                phase="analysis",
                summary="旧领域结论",
                conclusion="历史：订单域路由错误",
                evidence_chain=[],
                confidence=0.5,
                raw_output={},
            )
        ],
        discussion_step_count=2,
        max_discussion_steps=8,
        dialogue_items=[
            {
                "speaker": "CodeAgent",
                "phase": "analysis",
                "conclusion": "最新：连接池泄漏导致CPU飙升",
                "message": "连接池没及时释放。",
            }
        ],
    )

    assert "CodeAgent" in prompt
    assert "连接池泄漏" in prompt


def test_round_cards_for_routing_falls_back_to_messages_when_history_empty():
    """验证轮次cardsfor路由fallsbackto消息当历史空。"""
    
    orchestrator = _orchestrator()
    cards = orchestrator._round_cards_for_routing(
        {
            "history_cards": [],
            "round_start_turn_index": 0,
            "messages": [
                AIMessage(
                    content="我确认连接池耗尽是关键线索",
                    name="LogAgent",
                    additional_kwargs={
                        "agent_name": "LogAgent",
                        "phase": "analysis",
                        "conclusion": "连接池耗尽",
                        "confidence": 0.78,
                    },
                )
            ],
        }
    )

    assert len(cards) == 1
    assert cards[0].agent_name == "LogAgent"
    assert "连接池耗尽" in cards[0].conclusion


def test_derive_conversation_state_with_messages_and_existing_outputs():
    """验证deriveconversation状态带消息andexistingoutputs。"""
    
    orchestrator = _orchestrator()
    state = orchestrator._derive_conversation_state_with_context(
        [],
        messages=[
            AIMessage(
                content="我确认是连接池泄漏导致CPU飙升",
                name="CodeAgent",
                additional_kwargs={
                    "agent_name": "CodeAgent",
                    "phase": "analysis",
                    "conclusion": "连接池泄漏",
                    "confidence": 0.81,
                },
            )
        ],
        existing_agent_outputs={
            "ProblemAnalysisAgent": {
                "confidence": 0.77,
                "open_questions": ["是否存在慢SQL放大效应"],
            }
        },
    )

    assert "CodeAgent" in state["agent_outputs"]
    assert "ProblemAnalysisAgent" in state["agent_outputs"]
    assert any(claim.get("agent_name") == "CodeAgent" for claim in state["claims"])


def test_build_agent_prompt_prefers_dialogue_items():
    """验证buildAgentPromptprefersdialogueitems。"""
    
    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="CodeAgent",
        role="代码分析专家",
        phase="analysis",
        system_prompt="test",
    )
    prompt = orchestrator._build_agent_prompt(
        spec=spec,
        loop_round=1,
        context={"service": "order-service"},
        history_cards=[],
        assigned_command=None,
        dialogue_items=[
            {
                "speaker": "LogAgent",
                "phase": "analysis",
                "conclusion": "线程池阻塞",
                "message": "线程池队列长度持续拉高。",
            }
        ],
        inbox_messages=[
            {
                "sender": "ProblemAnalysisAgent",
                "receiver": "CodeAgent",
                "message_type": "command",
                "content": {"task": "检查连接池释放逻辑"},
            }
        ],
    )

    assert "LogAgent" in prompt
    assert "线程池阻塞" in prompt
    assert "你收到的消息" in prompt
    assert "连接池释放逻辑" in prompt


def test_build_collaboration_prompt_prefers_dialogue_items():
    """验证buildcollaborationPromptprefersdialogueitems。"""
    
    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="DomainAgent",
        role="领域映射专家",
        phase="analysis",
        system_prompt="test",
    )
    prompt = orchestrator._build_collaboration_prompt(
        spec=spec,
        loop_round=1,
        context={"service": "order-service"},
        peer_cards=[],
        assigned_command=None,
        dialogue_items=[
            {
                "speaker": "CodeAgent",
                "phase": "analysis",
                "conclusion": "连接池泄漏",
                "message": "我确认连接池释放路径有缺陷。",
            }
        ],
        inbox_messages=[
            {
                "sender": "LogAgent",
                "receiver": "DomainAgent",
                "message_type": "evidence",
                "content": {"conclusion": "线程池拥塞"},
            }
        ],
    )

    assert "CodeAgent" in prompt
    assert "连接池泄漏" in prompt
    assert "你收到的消息" in prompt
    assert "线程池拥塞" in prompt


def test_create_missing_evidence_turn_marks_payload_as_missing():
    """验证创建缺失证据turn标记载荷as缺失。"""
    
    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="DatabaseAgent",
        role="数据库取证专家",
        phase="analysis",
        system_prompt="test",
    )

    turn = asyncio.run(
        orchestrator._create_missing_evidence_turn(
            spec=spec,
            prompt="test prompt",
            round_number=1,
            loop_round=1,
            tool_name="db_snapshot_reader",
            tool_status="disabled",
            reason="数据库工具未启用",
        )
    )

    assert turn.output_content["degraded"] is True
    assert turn.output_content["evidence_status"] == "missing"
    assert turn.output_content["tool_status"] == "disabled"
    assert "证据未采集完成" in turn.output_content["conclusion"]


def test_apply_tool_limited_semantics_keeps_llm_analysis_when_tool_unavailable():
    """验证apply工具受限semantics保留LLM分析当工具unavailable。"""
    
    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="DatabaseAgent",
        role="数据库取证专家",
        phase="analysis",
        system_prompt="test",
    )
    turn = DebateTurn(
        round_number=1,
        phase="analysis",
        agent_name="DatabaseAgent",
        agent_role="数据库取证专家",
        model={"name": "glm-5"},
        input_message="",
        output_content={
            "chat_message": "我先看现有 SQL 和锁等待现象。",
            "analysis": "已有日志显示 lock wait timeout，并且订单接口在数据库阶段超时。",
            "conclusion": "数据库锁等待仍是最高优先级怀疑方向。",
            "confidence": 0.78,
            "next_checks": ["确认 ipc_orders_t 最近锁冲突"],
        },
        confidence=0.78,
    )

    updated = orchestrator._apply_tool_limited_semantics(
        turn=turn,
        spec=spec,
        assigned_command={"task": "检查数据库锁等待", "use_tool": True},
        context_with_tools={
            "investigation_leads": {
                "database_tables": ["ipc_orders_t"],
                "api_endpoints": ["/api/v1/orders"],
            },
            "tool_context": {
                "name": "db_snapshot_reader",
                "used": False,
                "enabled": False,
                "status": "disabled",
                "summary": "数据库工具未启用",
                "command_gate": {"has_command": True, "allow_tool": True},
            },
        },
    )

    assert updated.output_content["degraded"] is True
    assert updated.output_content["evidence_status"] == "inferred_without_tool"
    assert updated.output_content["tool_status"] == "disabled"
    assert "受限分析" in updated.output_content["analysis"]
    assert "ipc_orders_t" in updated.output_content["missing_info"]
    assert updated.output_content["confidence"] <= 0.58


def test_apply_tool_limited_semantics_keeps_context_grounded_output_effective():
    """工具受限但共享证据充分时，不应把有效结论一律打成硬降级。"""

    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="CodeAgent",
        role="代码分析专家",
        phase="analysis",
        system_prompt="test",
    )
    turn = DebateTurn(
        round_number=1,
        phase="analysis",
        agent_name="CodeAgent",
        agent_role="代码分析专家",
        model={"name": "glm-5"},
        input_message="",
        output_content={
            "chat_message": "我先基于 code diff 和共享日志重建链路。",
            "analysis": (
                "shared context 已明确给出 code diff summary：promotionClient.checkQuota 被移入 "
                "@Transactional createOrder 内，且日志显示 checkQuota 耗时升高、随后 HikariPool 获取超时。"
            ),
            "conclusion": "代码变更扩大事务边界是主因，数据库锁等待只是被放大的次级现象。",
            "confidence": 0.72,
            "evidence_chain": [
                "Code diff summary: promotionClient.checkQuota moved into @Transactional createOrder",
                "HikariPool timeout after promotionClient.checkQuota latency spike",
            ],
            "code_evidence_anchors": [
                "OrderService#createOrder",
                "promotionClient.checkQuota",
            ],
            "next_checks": ["恢复 git_tool 后核对提交 commit 与方法签名"],
        },
        confidence=0.72,
    )

    updated = orchestrator._apply_tool_limited_semantics(
        turn=turn,
        spec=spec,
        assigned_command={"task": "定位事务边界变更", "use_tool": True},
        context_with_tools={
            "shared_context": {
                "incident_summary": {
                    "title": "orders 502 after release",
                    "symptom": "promotion latency spike then Hikari timeout",
                },
                "log_excerpt": (
                    "promotionClient.checkQuota cost=1847ms\n"
                    "HikariPool-1 - Connection is not available, request timed out after 3000ms"
                ),
                "code_diff_summary": (
                    "promotionClient.checkQuota moved inside @Transactional createOrder"
                ),
                "db_wait_summary": "row lock wait increased on inventory_reservation for hotspot sku",
            },
            "focused_context": {
                "mapped_code_scope": {
                    "code_artifacts": ["order/OrderService.java"],
                }
            },
            "investigation_leads": {
                "class_names": ["OrderService"],
                "code_artifacts": ["order/OrderService.java"],
                "api_endpoints": ["/api/v1/orders"],
            },
            "tool_context": {
                "name": "git_tool",
                "used": False,
                "enabled": False,
                "status": "disabled",
                "summary": "git 工具未启用",
                "command_gate": {"has_command": True, "allow_tool": True},
            },
        },
    )

    assert updated.output_content["tool_status"] == "disabled"
    assert updated.output_content["tool_name"] == "git_tool"
    assert updated.output_content["evidence_status"] == "context_grounded_without_tool"
    assert updated.output_content["degraded"] is False
    assert updated.output_content["confidence"] >= 0.66


def test_apply_tool_limited_semantics_accepts_context_grounded_output_without_top_level_evidence_chain():
    """真实样本常把证据写在分析文本里，不能因为缺少顶层 evidence_chain 就硬降级。"""

    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="LogAgent",
        role="日志分析专家",
        phase="analysis",
        system_prompt="test",
    )
    turn = DebateTurn(
        round_number=1,
        phase="analysis",
        agent_name="LogAgent",
        agent_role="日志分析专家",
        model={"name": "glm-5"},
        input_message="",
        output_content={
            "chat_message": "我先基于共享日志恢复时间线。",
            "analysis": (
                "日志已给出完整顺序：10:08:09 promotionClient.checkQuota 1847ms，"
                "10:08:10 inventory reservation waiting lock，10:08:11 HikariPool timeout，"
                "10:08:12 gateway 502。这说明远程调用阻塞事务后，锁等待和连接池耗尽依次出现。"
            ),
            "conclusion": "日志链路支持“长事务先出现，数据库锁等待只是放大器”这一判断。",
            "confidence": 0.72,
            "next_checks": [
                "恢复日志工具后补拉完整 traceId=deb_342d8ae3fce5 调用链",
                "请 CodeAgent 确认 @Transactional 具体位置",
            ],
        },
        confidence=0.72,
    )

    updated = orchestrator._apply_tool_limited_semantics(
        turn=turn,
        spec=spec,
        assigned_command={"task": "重建事务与远程调用时间线", "use_tool": True},
        context_with_tools={
            "shared_context": {
                "incident_summary": {
                    "title": "orders 502 after release",
                    "symptom": "promotion latency spike then Hikari timeout",
                },
                "log_excerpt": (
                    "10:08:09 promotionClient.checkQuota cost=1847ms\n"
                    "10:08:10 waiting lock\n"
                    "10:08:11 HikariPool timeout\n"
                    "10:08:12 gateway 502"
                ),
            },
            "focused_context": {
                "log_scope": {"trace_id": "deb_342d8ae3fce5"},
            },
            "investigation_leads": {
                "trace_ids": ["deb_342d8ae3fce5"],
                "api_endpoints": ["/api/v1/orders"],
            },
            "tool_context": {
                "name": "local_log_reader",
                "used": False,
                "enabled": False,
                "status": "disabled",
                "summary": "日志工具未启用",
                "command_gate": {"has_command": True, "allow_tool": True},
            },
        },
    )

    assert updated.output_content["evidence_status"] == "context_grounded_without_tool"
    assert updated.output_content["degraded"] is False
    assert updated.output_content["confidence"] >= 0.66


def test_apply_tool_limited_semantics_accepts_logagent_first_round_conservative_confidence():
    """LogAgent 首轮常因缺少 trace 实采而保守打分，但因果链明确时不应被硬降级。"""

    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="LogAgent",
        role="日志分析专家",
        phase="analysis",
        system_prompt="test",
    )
    turn = DebateTurn(
        round_number=1,
        phase="analysis",
        agent_name="LogAgent",
        agent_role="日志分析专家",
        model={"name": "glm-5"},
        input_message="",
        output_content={
            "chat_message": "我先基于共享日志恢复时间线。",
            "analysis": (
                "日志已给出完整顺序：10:08:09 promotionClient.checkQuota 1847ms，"
                "10:08:10 inventory reservation waiting lock，10:08:11 HikariPool timeout。"
                "这条因果链支持“长事务先出现，数据库锁等待只是放大器”的判断。"
                "当前缺少 trace span 反证，但不足以推翻现有结论。"
            ),
            "conclusion": "日志链路支持代码把远程调用放进事务内，数据库锁等待不是原发根因。",
            "confidence": 0.58,
        },
        confidence=0.58,
    )

    updated = orchestrator._apply_tool_limited_semantics(
        turn=turn,
        spec=spec,
        assigned_command={"task": "重建事务与远程调用时间线", "use_tool": True},
        context_with_tools={
            "shared_context": {
                "incident_summary": {
                    "title": "orders 502 after release",
                    "symptom": "promotion latency spike then Hikari timeout",
                },
                "log_excerpt": (
                    "10:08:09 promotionClient.checkQuota cost=1847ms\n"
                    "10:08:10 inventory waiting lock\n"
                    "10:08:11 HikariPool timeout"
                ),
            },
            "focused_context": {
                "log_scope": {"trace_id": "deb_log_first_round"},
            },
            "investigation_leads": {
                "trace_ids": ["deb_log_first_round"],
                "api_endpoints": ["/api/v1/orders"],
            },
            "tool_context": {
                "name": "local_log_reader",
                "used": False,
                "enabled": False,
                "status": "disabled",
                "summary": "日志工具未启用",
                "command_gate": {"has_command": True, "allow_tool": True},
            },
        },
    )

    assert updated.output_content["evidence_status"] == "context_grounded_without_tool"
    assert updated.output_content["degraded"] is False
    assert updated.output_content["confidence"] >= 0.62


def test_apply_tool_limited_semantics_accepts_databaseagent_amplifier_judgment_with_conservative_confidence():
    """DatabaseAgent 若已明确说明数据库只是放大器，不应因 0.52 置信度继续整轮重跑。"""

    orchestrator = _orchestrator()
    spec = AgentSpec(
        name="DatabaseAgent",
        role="数据库分析专家",
        phase="analysis",
        system_prompt="test",
    )
    turn = DebateTurn(
        round_number=1,
        phase="analysis",
        agent_name="DatabaseAgent",
        agent_role="数据库分析专家",
        model={"name": "glm-5"},
        input_message="",
        output_content={
            "chat_message": "我先按共享上下文判断数据库角色。",
            "analysis": (
                "SQL explain 正常，锁等待出现在 promotionClient.checkQuota 1847ms 之后，"
                "HikariPool timeout 又发生在锁等待之后。这符合“上游长事务拖长锁持有时间，"
                "数据库成为放大器而不是原发根因”的模式。反证方面，没有看到索引失效或 full scan。"
            ),
            "conclusion": "数据库锁等待是次级放大器，不是原发根因；主因仍是事务内远程调用。",
            "confidence": 0.52,
        },
        confidence=0.52,
    )

    updated = orchestrator._apply_tool_limited_semantics(
        turn=turn,
        spec=spec,
        assigned_command={"task": "判断数据库是根因还是放大器", "use_tool": True},
        context_with_tools={
            "shared_context": {
                "incident_summary": {
                    "title": "orders 502 after release",
                    "symptom": "db locks and hikari alerts",
                },
                "log_excerpt": (
                    "promotionClient.checkQuota cost=1847ms\n"
                    "inventory reservation waiting lock\n"
                    "HikariPool timeout"
                ),
                "db_wait_summary": "row lock wait increased on inventory_reservation hotspot sku",
            },
            "focused_context": {
                "target_tables": ["t_order", "t_order_item", "t_order_snapshot"],
            },
            "investigation_leads": {
                "database_tables": ["t_order", "t_order_item", "t_order_snapshot"],
                "class_names": ["HikariPool"],
            },
            "tool_context": {
                "name": "db_snapshot_reader",
                "used": False,
                "enabled": False,
                "status": "disabled",
                "summary": "数据库工具未启用",
                "command_gate": {"has_command": True, "allow_tool": True},
            },
        },
    )

    assert updated.output_content["evidence_status"] == "context_grounded_without_tool"
    assert updated.output_content["degraded"] is False
    assert updated.output_content["confidence"] >= 0.62


def test_commander_prompt_can_use_existing_agent_outputs():
    """验证主AgentPrompt可以useexistingAgentoutputs。"""
    
    orchestrator = _orchestrator()
    prompt = orchestrator._build_problem_analysis_commander_prompt(
        loop_round=1,
        context={"service": "order-service"},
        history_cards=[],
        dialogue_items=[],
        existing_agent_outputs={
            "LogAgent": {
                "analysis": "日志显示请求在线程池等待时间持续升高",
                "conclusion": "线程池阻塞",
                "confidence": 0.82,
            }
        },
    )

    assert "LogAgent" in prompt
    assert "线程池阻塞" in prompt


def test_enrich_agent_commands_passes_mapped_tables_to_database_agent():
    """验证enrichAgentcommandspassesmappedtablestodatabaseAgent。"""
    
    orchestrator = _orchestrator()
    commands = {
        "DatabaseAgent": {
            "target_agent": "DatabaseAgent",
            "task": "读取数据库结构",
            "focus": "",
            "expected_output": "",
            "use_tool": True,
        }
    }
    compact_context = {
        "interface_mapping": {
            "matched": True,
            "database_tables": ["public.t_order", "t_order_item"],
        }
    }
    enriched = orchestrator._enrich_agent_commands_with_asset_mapping(commands, compact_context)
    db_cmd = enriched["DatabaseAgent"]

    assert db_cmd["database_tables"] == ["public.t_order", "t_order_item"]
    assert "责任田映射表" in str(db_cmd["focus"] or "")


def test_enrich_agent_commands_forces_tools_for_key_evidence_agents():
    """验证命中责任田线索时关键证据型Agent不会被关闭工具。"""

    orchestrator = _orchestrator()
    commands = {
        "LogAgent": {
            "target_agent": "LogAgent",
            "task": "先基于已有信息总结",
            "focus": "",
            "expected_output": "",
            "use_tool": False,
        },
        "CodeAgent": {
            "target_agent": "CodeAgent",
            "task": "梳理代码路径",
            "focus": "",
            "expected_output": "",
            "use_tool": False,
        },
        "DatabaseAgent": {
            "target_agent": "DatabaseAgent",
            "task": "确认数据库瓶颈",
            "focus": "",
            "expected_output": "",
            "use_tool": False,
        },
        "ChangeAgent": {
            "target_agent": "ChangeAgent",
            "task": "看最近变更",
            "focus": "",
            "expected_output": "",
            "use_tool": False,
        },
    }
    compact_context = {
        "investigation_leads": {
            "api_endpoints": ["POST /api/v1/orders"],
            "service_names": ["order-service"],
            "trace_ids": ["trace-001"],
            "error_keywords": ["HikariPool timeout"],
            "class_names": ["OrderService"],
            "code_artifacts": ["services/order-service/src/main/java/com/acme/order/OrderService.java"],
            "database_tables": ["public.t_order", "public.t_order_item"],
        }
    }

    enriched = orchestrator._enrich_agent_commands_with_asset_mapping(commands, compact_context)

    for agent_name in ("LogAgent", "CodeAgent", "DatabaseAgent", "ChangeAgent"):
        assert enriched[agent_name]["use_tool"] is True
        assert enriched[agent_name]["tool_requirement"] == "required_by_investigation_leads"


def test_extract_agent_commands_preserves_skill_hints_and_tables():
    """验证提取AgentcommandspreservesSkill提示andtables。"""
    
    orchestrator = _orchestrator()
    payload = {
        "commands": [
            {
                "target_agent": "DatabaseAgent",
                "task": "检查锁等待",
                "focus": "锁和慢SQL",
                "expected_output": "锁链路+索引评估",
                "use_tool": True,
                "database_tables": ["public.t_order", "public.t_order_item"],
                "skill_hints": ["db-bottleneck-diagnosis"],
            }
        ]
    }
    commands = orchestrator._extract_agent_commands_from_payload(payload, fill_defaults=False)
    db_cmd = commands["DatabaseAgent"]
    assert db_cmd["database_tables"] == ["public.t_order", "public.t_order_item"]
    assert db_cmd["skill_hints"] == ["db-bottleneck-diagnosis"]


def test_enrich_agent_commands_adds_default_skill_hints():
    """验证enrichAgentcommandsadds默认Skill提示。"""
    
    orchestrator = _orchestrator()
    commands = {
        "LogAgent": {
            "target_agent": "LogAgent",
            "task": "分析日志",
            "focus": "",
            "expected_output": "",
            "use_tool": True,
            "database_tables": [],
            "skill_hints": [],
        },
        "DatabaseAgent": {
            "target_agent": "DatabaseAgent",
            "task": "分析数据库",
            "focus": "",
            "expected_output": "",
            "use_tool": True,
            "database_tables": ["public.t_order"],
            "skill_hints": [],
        },
        "MetricsAgent": {
            "target_agent": "MetricsAgent",
            "task": "分析指标",
            "focus": "",
            "expected_output": "",
            "use_tool": True,
            "database_tables": [],
            "skill_hints": [],
        },
        "RuleSuggestionAgent": {
            "target_agent": "RuleSuggestionAgent",
            "task": "建议告警规则",
            "focus": "",
            "expected_output": "",
            "use_tool": True,
            "database_tables": [],
            "skill_hints": [],
        },
    }
    compact_context = {
        "incident": {
            "title": "/orders 502",
            "description": "Hikari connection timeout and SQL lock wait",
        },
        "log_excerpt": "lock wait timeout exceeded",
    }
    enriched = orchestrator._enrich_agent_commands_with_skill_hints(commands, compact_context)
    assert enriched["LogAgent"]["skill_hints"] == ["log-forensics"]
    assert enriched["DatabaseAgent"]["skill_hints"] == ["db-bottleneck-diagnosis"]
    assert enriched["MetricsAgent"]["skill_hints"] == ["metrics-anomaly-triage"]
    assert enriched["RuleSuggestionAgent"]["skill_hints"] == ["alert-rule-hardening"]


def test_enrich_agent_commands_does_not_override_existing_skill_hints():
    """验证enrichAgentcommandsdoesnotoverrideexistingSkill提示。"""
    
    orchestrator = _orchestrator()
    commands = {
        "CodeAgent": {
            "target_agent": "CodeAgent",
            "task": "定位代码问题",
            "focus": "",
            "expected_output": "",
            "use_tool": True,
            "database_tables": [],
            "skill_hints": ["custom-skill"],
        }
    }
    enriched = orchestrator._enrich_agent_commands_with_skill_hints(commands, {"incident": {"title": "404"}})
    assert enriched["CodeAgent"]["skill_hints"] == ["custom-skill"]


def test_enrich_agent_commands_with_investigation_leads():
    """验证enrichAgentcommands带investigation线索。"""
    
    orchestrator = _orchestrator()
    commands = {
        "LogAgent": {"target_agent": "LogAgent", "task": "分析日志", "focus": "", "expected_output": ""},
        "CodeAgent": {"target_agent": "CodeAgent", "task": "分析代码", "focus": "", "expected_output": ""},
        "DatabaseAgent": {"target_agent": "DatabaseAgent", "task": "分析数据库", "focus": "", "expected_output": ""},
        "MetricsAgent": {"target_agent": "MetricsAgent", "task": "分析指标", "focus": "", "expected_output": ""},
    }
    compact_context = {
        "investigation_leads": {
            "api_endpoints": ["POST /api/v1/orders"],
            "service_names": ["order-service"],
            "code_artifacts": ["order/service/OrderService.java"],
            "class_names": ["OrderController", "OrderService"],
            "database_tables": ["t_order", "t_order_item"],
            "monitor_items": ["order.error.rate", "order.latency.p99"],
            "dependency_services": ["inventory-service"],
            "trace_ids": ["trace-001"],
            "error_keywords": ["timeout", "inventory-service"],
            "domain": "order",
            "aggregate": "Order",
            "owner_team": "order-sre",
            "owner": "neo",
        }
    }

    enriched = orchestrator._enrich_agent_commands_with_asset_mapping(commands, compact_context)

    assert enriched["LogAgent"]["api_endpoints"] == ["POST /api/v1/orders"]
    assert enriched["LogAgent"]["trace_ids"] == ["trace-001"]
    assert "错误时间线" in enriched["LogAgent"]["expected_output"]
    assert enriched["CodeAgent"]["class_names"] == ["OrderController", "OrderService"]
    assert enriched["CodeAgent"]["code_artifacts"] == ["order/service/OrderService.java"]
    assert enriched["DatabaseAgent"]["database_tables"] == ["t_order", "t_order_item"]
    assert enriched["MetricsAgent"]["monitor_items"] == ["order.error.rate", "order.latency.p99"]


def test_judge_timeout_plan_has_retry_in_quick_mode():
    """验证裁决超时planhasretryinquick模式。"""
    
    orchestrator = _orchestrator()
    orchestrator._require_verification_plan = False
    plan = orchestrator._agent_timeout_plan("JudgeAgent")
    assert len(plan) == 2
    assert float(plan[1]) >= float(plan[0])


def test_queue_timeout_prioritizes_commander_and_judge():
    """验证队列超时prioritizes主Agentand裁决。"""
    
    orchestrator = _orchestrator()

    analysis_timeout = orchestrator._agent_queue_timeout("LogAgent")
    commander_timeout = orchestrator._agent_queue_timeout("ProblemAnalysisAgent")
    judge_timeout = orchestrator._agent_queue_timeout("JudgeAgent")

    assert commander_timeout > analysis_timeout
    assert judge_timeout > commander_timeout


def test_investigation_full_first_round_commander_gets_extra_queue_time_and_lower_token_budget():
    """验证 investigation_full 首轮 commander 拿到更高排队预算和更紧 token 上限。"""

    orchestrator = _orchestrator()
    orchestrator._deployment_profile_name = "investigation_full"
    orchestrator.turns = []

    first_round_timeout = orchestrator._agent_queue_timeout("ProblemAnalysisAgent")
    first_round_tokens = orchestrator._agent_max_tokens("ProblemAnalysisAgent")

    orchestrator.turns = [object()]
    later_round_timeout = orchestrator._agent_queue_timeout("ProblemAnalysisAgent")
    later_round_tokens = orchestrator._agent_max_tokens("ProblemAnalysisAgent")

    assert first_round_timeout >= 50.0
    assert first_round_timeout > later_round_timeout
    assert first_round_tokens <= 360
    assert later_round_tokens >= 520


def test_fast_mode_first_round_commander_uses_compact_budget():
    """验证 quick/background 首轮主Agent使用更紧凑的初始预算。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "background"
    orchestrator._require_verification_plan = False
    orchestrator.turns = []

    first_round_tokens = orchestrator._agent_max_tokens("ProblemAnalysisAgent")
    first_round_timeout_plan = orchestrator._agent_timeout_plan("ProblemAnalysisAgent")

    assert first_round_tokens <= 480
    assert first_round_timeout_plan == [60.0]


def test_fast_mode_first_round_analysis_agents_use_compact_budget():
    """验证 quick/background 首轮关键分析Agent使用更紧凑预算。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "background"
    orchestrator._require_verification_plan = False
    orchestrator.turns = [type("Turn", (), {"agent_name": "ProblemAnalysisAgent"})()]

    for agent_name in ("LogAgent", "CodeAgent", "DatabaseAgent", "DomainAgent"):
        assert orchestrator._agent_max_tokens(agent_name) <= 480
        assert orchestrator._agent_timeout_plan(agent_name) == [60.0]
        assert orchestrator._agent_queue_timeout(agent_name) >= 60.0


def test_analysis_depth_mode_assigns_default_rounds_when_not_overridden():
    """验证分析深度模式会给会话分配默认轮次。"""

    quick = LangGraphRuntimeOrchestrator(
        consensus_threshold=0.75,
        max_rounds=0,
        analysis_depth_mode="quick",
    )
    standard = LangGraphRuntimeOrchestrator(
        consensus_threshold=0.75,
        max_rounds=0,
        analysis_depth_mode="standard",
    )
    deep = LangGraphRuntimeOrchestrator(
        consensus_threshold=0.75,
        max_rounds=0,
        analysis_depth_mode="deep",
    )

    assert quick.analysis_depth_mode == "quick"
    assert quick.max_rounds == 1
    assert standard.max_rounds >= 2
    assert deep.max_rounds >= 4


def test_analysis_depth_mode_keeps_explicit_round_override():
    """验证显式指定 max_rounds 时不会被深度模式默认值覆盖。"""

    orchestrator = LangGraphRuntimeOrchestrator(
        consensus_threshold=0.75,
        max_rounds=6,
        analysis_depth_mode="deep",
    )

    assert orchestrator.analysis_depth_mode == "deep"
    assert orchestrator.max_rounds == 6


def test_quick_mode_analysis_prompt_is_precompacted():
    """验证 quick 模式分析Agent在首次执行前就会压缩超长 Prompt。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "quick"
    orchestrator._require_verification_plan = False
    orchestrator.turns = []
    spec = AgentSpec(
        name="CodeAgent",
        role="代码分析专家",
        phase="analysis",
        system_prompt="test",
    )

    huge_context = {
        "service": "order-service",
        "log_excerpt": "x" * 5000,
        "interface_mapping": {"code_artifacts": ["OrderController#createOrder"] * 60},
        "focused_context": {"method_call_chain": [f"OrderService#call{i}" for i in range(60)]},
    }

    prompt = orchestrator._build_agent_prompt(
        spec=spec,
        loop_round=1,
        context=huge_context,
        history_cards=[],
        assigned_command={"task": "分析代码路径", "focus": "连接池与事务", "expected_output": "根因"},
        dialogue_items=[],
        inbox_messages=[],
    )

    assert len(prompt) <= 2500
    assert "中间上下文在超时重试时已压缩" in prompt


def test_quick_mode_analysis_prompt_keeps_shared_evidence_blocks():
    """验证 quick 模式压缩后仍保留共享上下文和关键证据，而不是只剩首尾碎片。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "quick"
    orchestrator._require_verification_plan = False
    orchestrator.turns = []
    spec = AgentSpec(
        name="LogAgent",
        role="日志分析专家",
        phase="analysis",
        system_prompt="test",
    )

    prompt = orchestrator._build_agent_prompt(
        spec=spec,
        loop_round=1,
        context={
            "shared_context": {
                "incident_summary": {
                    "title": "下单 502 + 数据库锁等待误导",
                    "service_name": "order-service",
                },
                "log_excerpt": (
                    "2026-03-10T10:08:09.944+08:00 WARN promotionClient.checkQuota cost=1847ms sku=sku_10017\n"
                    "2026-03-10T10:08:10.118+08:00 WARN inventory reservation update waiting lock sku=sku_10017\n"
                    "2026-03-10T10:08:11.203+08:00 ERROR HikariPool connection timeout"
                ),
                "interface_mapping": {
                    "matched": True,
                    "endpoint": {"method": "POST", "path": "/api/v1/orders"},
                    "database_tables": ["t_order", "t_order_item", "t_order_snapshot"],
                },
            },
            "focused_context": {
                "analysis_objective": {
                    "task": "重建起因事件到用户故障的时间线",
                    "focus": "区分事务边界问题和数据库放大效应",
                }
            },
        },
        history_cards=[],
        assigned_command={
            "task": "提取故障时间窗口内ERROR/FATAL级别日志，定位首个异常堆栈",
            "focus": "异常类型、抛出位置、调用链上游服务、时间戳序列",
            "expected_output": "异常摘要",
        },
        dialogue_items=[
            {
                "speaker": "CodeAgent",
                "phase": "analysis",
                "message": "无上下文时我只能先补证。" * 80,
                "conclusion": "证据不足",
                "confidence": 0.15,
            }
        ],
        inbox_messages=[],
    )

    assert len(prompt) <= 2500
    assert "共享上下文：" in prompt
    assert "promotionClient.checkQuota cost=1847ms" in prompt
    assert "/api/v1/orders" in prompt
    assert "Agent 专属分析上下文：" in prompt
    assert "区分事务边界问题和数据库放大效应" in prompt


def test_quick_mode_analysis_prompt_keeps_tail_code_diff_evidence():
    """验证共享上下文压缩后仍保留日志尾部的 code diff 关键证据。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "quick"
    orchestrator._require_verification_plan = False
    orchestrator.turns = []
    spec = AgentSpec(
        name="CodeAgent",
        role="代码分析专家",
        phase="analysis",
        system_prompt="test",
    )

    prompt = orchestrator._build_agent_prompt(
        spec=spec,
        loop_round=1,
        context={
            "shared_context": {
                "incident_summary": {
                    "title": "下单 502 + 数据库锁等待误导",
                    "service_name": "order-service",
                },
                "log_excerpt": (
                    "2026-03-10T10:08:09.944+08:00 WARN promotionClient.checkQuota cost=1847ms sku=sku_10017\n"
                    "2026-03-10T10:08:10.118+08:00 WARN inventory reservation update waiting lock sku=sku_10017\n"
                    "2026-03-10T10:08:11.203+08:00 ERROR HikariPool request timed out after 3000ms\n"
                    "DB wait summary: row lock wait count 15/min -> 2200/min\n"
                    "Code diff summary: old flow executed promotionClient.checkQuota before transactionTemplate.execute; "
                    "new flow is @Transactional createOrder() and calls promotionClient.checkQuota inside transaction "
                    "before orderRepository.insert and inventoryReservationRepository.reserve."
                ),
                "interface_mapping": {
                    "matched": True,
                    "endpoint": {"method": "POST", "path": "/api/v1/orders"},
                    "database_tables": ["t_order", "t_order_item", "t_order_snapshot"],
                },
                "investigation_leads": {
                    "code_artifacts": ["OrderAppService#createOrder", "OrderRepositoryImpl#save"],
                },
            },
            "focused_context": {
                "analysis_objective": {
                    "task": "定位事务边界扩张导致的连接占用",
                    "focus": "验证 promotionClient.checkQuota 是否被移入事务",
                }
            },
        },
        history_cards=[],
        assigned_command={
            "task": "对比新旧版本的事务边界和远程调用位置",
            "focus": "checkQuota、@Transactional、inventoryReservationRepository.reserve",
            "expected_output": "代码锚点与因果链",
        },
        dialogue_items=[],
        inbox_messages=[],
    )

    assert "Code diff summary" in prompt
    assert "@Transactional" in prompt
    assert "transactionTemplate.execute" in prompt


def test_quick_mode_commander_prompt_keeps_incident_context_blocks():
    """验证 quick 模式下主Agent压缩后仍保留故障上下文，而不是只剩空模板和输出 schema。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "quick"
    orchestrator._require_verification_plan = False
    orchestrator.turns = []

    prompt = orchestrator._build_problem_analysis_commander_prompt(
        loop_round=1,
        context={
            "incident_summary": {
                "title": "下单 502 + 数据库锁等待误导",
                "description": "发布后下单失败，真实根因是事务边界过长。",
                "severity": "high",
                "service_name": "order-service",
            },
            "log_excerpt": (
                "promotionClient.checkQuota cost=1847ms\n"
                "inventory reservation update waiting lock\n"
                "HikariPool request timed out"
            ),
            "available_analysis_agents": ["LogAgent", "CodeAgent", "DatabaseAgent"],
            "interface_mapping": {
                "matched": True,
                "database_tables": ["t_order", "t_order_item", "t_order_snapshot"],
                "endpoint": {"method": "POST", "path": "/api/v1/orders"},
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "code_artifacts": ["OrderAppService#createOrder"],
            },
        },
        history_cards=[],
        dialogue_items=[
            {
                "speaker": "LogAgent",
                "phase": "analysis",
                "message": "日志不足时要补证。" * 80,
                "conclusion": "证据不足",
                "confidence": 0.15,
            }
        ],
    )

    assert len(prompt) <= 1900
    assert "故障上下文:" in prompt
    assert "promotionClient.checkQuota cost=1847ms" in prompt
    assert "/api/v1/orders" in prompt
    assert "t_order_item" in prompt


def test_quick_mode_commander_prompt_keeps_tail_root_cause_hints():
    """验证 commander 的故障上下文压缩后仍保留尾部根因提示而不是只剩前半段日志。"""

    orchestrator = _orchestrator()
    orchestrator._execution_mode_name = "quick"
    orchestrator._require_verification_plan = False
    orchestrator.turns = []

    prompt = orchestrator._build_problem_analysis_commander_prompt(
        loop_round=1,
        context={
            "incident_summary": {
                "title": "下单 502 + 数据库锁等待误导",
                "description": "发布后下单失败，真实根因是事务边界过长，数据库只是放大器。",
                "severity": "high",
                "service_name": "order-service",
            },
            "log_excerpt": (
                "promotionClient.checkQuota cost=1847ms\n"
                "inventory reservation update waiting lock\n"
                "HikariPool request timed out\n"
                "Code diff summary: old flow executed promotionClient.checkQuota before transactionTemplate.execute; "
                "new flow is @Transactional createOrder() and calls promotionClient.checkQuota inside transaction."
            ),
            "available_analysis_agents": ["LogAgent", "CodeAgent", "DatabaseAgent"],
            "interface_mapping": {
                "matched": True,
                "database_tables": ["t_order", "t_order_item", "t_order_snapshot"],
                "endpoint": {"method": "POST", "path": "/api/v1/orders"},
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "code_artifacts": ["OrderAppService#createOrder"],
            },
        },
        history_cards=[],
        dialogue_items=[],
    )

    assert "Code diff summary" in prompt
    assert "@Transactional" in prompt
    assert "数据库只是放大器" in prompt


def test_flatten_structured_state_view_preserves_context_summary_and_messages():
    """验证 flat 视图不会把 context_summary/messages 这类顶层核心字段吞掉。"""

    flat = flatten_structured_state_view(
        {
            "context": {"service_name": "order-service"},
            "context_summary": {
                "incident_summary": {
                    "title": "下单 502",
                    "service_name": "order-service",
                },
                "interface_mapping": {
                    "matched": True,
                    "database_tables": ["t_order", "t_order_item"],
                },
            },
            "messages": [
                AIMessage(
                    content="我看到 promotionClient.checkQuota 先慢后锁。",
                    name="LogAgent",
                )
            ],
            "phase_state": {"current_round": 1},
            "routing_state": {"next_step": "analysis_parallel"},
            "output_state": {"history_cards": []},
        }
    )

    assert flat["context_summary"]["incident_summary"]["title"] == "下单 502"
    assert flat["context_summary"]["interface_mapping"]["matched"] is True
    assert flat["context"]["service_name"] == "order-service"
    assert len(flat["messages"]) == 1


def test_investigation_full_key_evidence_agents_get_extra_queue_time():
    """验证完整调查模式会提高关键证据 Agent 的排队等待预算。"""

    orchestrator = _orchestrator()
    orchestrator._deployment_profile_name = "investigation_full"

    log_timeout = orchestrator._agent_queue_timeout("LogAgent")
    code_timeout = orchestrator._agent_queue_timeout("CodeAgent")
    db_timeout = orchestrator._agent_queue_timeout("DatabaseAgent")
    metrics_timeout = orchestrator._agent_queue_timeout("MetricsAgent")
    base_timeout = orchestrator._agent_queue_timeout("RunbookAgent")

    assert log_timeout >= 60.0
    assert code_timeout >= 60.0
    assert db_timeout >= 60.0
    assert metrics_timeout >= 90.0
    assert log_timeout > base_timeout
    assert metrics_timeout > log_timeout


def test_metrics_agent_queue_timeout_is_not_capped_by_base_timeout():
    """验证 MetricsAgent 不会退回到通用 30 秒队列超时。"""

    orchestrator = _orchestrator()

    metrics_timeout = orchestrator._agent_queue_timeout("MetricsAgent")
    base_timeout = orchestrator._agent_queue_timeout("RunbookAgent")

    assert base_timeout == float(max(2, int(settings.llm_queue_timeout)))
    assert metrics_timeout >= 75.0
    assert metrics_timeout > base_timeout


def test_default_timeout_baseline_is_relaxed_for_slow_llm_responses():
    """验证默认超时基线已整体上调，避免慢模型被过早截断。"""

    assert int(settings.llm_timeout) >= 180
    assert int(settings.llm_total_timeout) >= 90
    assert int(settings.llm_analysis_timeout) >= 55
    assert int(settings.llm_queue_timeout) >= 45
    assert int(settings.llm_analysis_queue_timeout) >= 60
    assert int(settings.llm_judge_queue_timeout) >= 90


def test_analysis_batch_limit_reserves_slot_for_settlement_agents():
    """验证分析batchlimitreservesslotforsettlementAgent。"""
    
    orchestrator = _orchestrator()
    orchestrator._llm_semaphore_limit = 3

    assert orchestrator._analysis_batch_limit(collaboration=False) == 2
    assert orchestrator._analysis_batch_limit(collaboration=True) == 2

    orchestrator._llm_semaphore_limit = 2
    assert orchestrator._analysis_batch_limit(collaboration=False) == 1

    orchestrator._deployment_profile_name = "investigation_full"
    orchestrator._llm_semaphore_limit = 4
    assert orchestrator._analysis_batch_limit(collaboration=False) == 2
    assert orchestrator._analysis_batch_limit(collaboration=True) == 1


def test_phase_executor_batches_by_priority_and_limit():
    """验证phaseexecutorbatchesby优先级andlimit。"""
    
    batches = PhaseExecutor._analysis_batches(
        ["DatabaseAgent", "MetricsAgent", "LogAgent", "CodeAgent", "DomainAgent"],
        [["DatabaseAgent", "MetricsAgent"], ["LogAgent", "CodeAgent"]],
        1,
    )

    assert batches == [
        ["DatabaseAgent"],
        ["MetricsAgent"],
        ["LogAgent"],
        ["CodeAgent"],
        ["DomainAgent"],
    ]


def test_build_top_k_hypotheses_prefers_high_confidence_expert_cards():
    """验证 Top-K 假设会优先保留高置信专家候选。"""

    orchestrator = _orchestrator()
    history_cards = [
        AgentEvidence(
            agent_name="LogAgent",
            phase="analysis",
            summary="日志结论",
            conclusion="连接池耗尽导致请求超时",
            evidence_chain=[],
            confidence=0.88,
            raw_output={},
        ),
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码结论",
            conclusion="事务边界过长放大了连接占用",
            evidence_chain=[],
            confidence=0.81,
            raw_output={},
        ),
        AgentEvidence(
            agent_name="CriticAgent",
            phase="critique",
            summary="质疑",
            conclusion="仍有替代解释",
            evidence_chain=[],
            confidence=0.4,
            raw_output={},
        ),
    ]

    top_k = orchestrator._build_top_k_hypotheses(history_cards)

    assert [item["agent_name"] for item in top_k[:2]] == ["LogAgent", "CodeAgent"]
    assert top_k[0]["conclusion"] == "连接池耗尽导致请求超时"


def test_compute_debate_stability_score_penalizes_gaps():
    """验证稳定度评分会被证据缺口和未收敛候选拉低。"""

    orchestrator = _orchestrator()
    score = orchestrator._compute_debate_stability_score(
        judge_confidence=0.82,
        evidence_coverage={"ok": 2, "degraded": 1, "missing": 1},
        top_k_hypotheses=[
            {"confidence": 0.85, "conclusion": "连接池耗尽"},
            {"confidence": 0.71, "conclusion": "线程池阻塞"},
        ],
        round_gap_summary=["仍有关键证据 Agent 缺失输出，需要补齐日志/代码/数据库/指标中的空缺。"],
    )

    assert 0.0 <= score < 0.8


@pytest.mark.asyncio
async def test_graph_round_evaluate_emits_coverage_and_convergence_fields(monkeypatch):
    """验证 round evaluate 会写回 coverage、Top-K、稳定度和回合目标。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=3)
    history_cards = [
        AgentEvidence(
            agent_name="LogAgent",
            phase="analysis",
            summary="日志结论",
            conclusion="连接池耗尽导致 502",
            evidence_chain=[],
            confidence=0.9,
            raw_output={"evidence_status": "ok"},
        ),
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码结论",
            conclusion="事务边界过长导致连接占用过高",
            evidence_chain=[],
            confidence=0.84,
            raw_output={"evidence_status": "ok"},
        ),
    ]
    judge_card = AgentEvidence(
        agent_name="JudgeAgent",
        phase="judgment",
        summary="裁决",
        conclusion="根因已基本收敛",
        evidence_chain=[],
        confidence=0.86,
        raw_output={},
    )

    async def _noop_emit(_: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(orchestrator, "_emit_event", _noop_emit)
    monkeypatch.setattr(orchestrator, "_history_cards_for_state", lambda state, limit=20: history_cards)
    monkeypatch.setattr(orchestrator, "_round_cards_from_state", lambda state: history_cards)
    monkeypatch.setattr(orchestrator, "_recent_judge_card", lambda cards: judge_card)

    result = await orchestrator._graph_round_evaluate(
        {
            "current_round": 2,
            "executed_rounds": 1,
            "supervisor_stop_requested": False,
        }
    )

    assert result["evidence_coverage"]["ok"] == 2
    assert result["top_k_hypotheses"][0]["agent_name"] == "LogAgent"
    assert result["debate_stability_score"] > 0.7
    assert result["continue_next_round"] is False
    assert result["round_objectives"]
    assert result["round_gap_summary"]


@pytest.mark.asyncio
async def test_graph_round_evaluate_deep_mode_requires_corroboration_to_stop(monkeypatch):
    """deep 模式下，没有旁证专家参与时不应过早收口。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=3)
    orchestrator.analysis_depth_mode = "deep"
    history_cards = [
        AgentEvidence(
            agent_name="LogAgent",
            phase="analysis",
            summary="日志结论",
            conclusion="连接池耗尽导致 502",
            evidence_chain=[],
            confidence=0.9,
            raw_output={"evidence_status": "ok"},
        ),
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码结论",
            conclusion="事务边界过长导致连接占用过高",
            evidence_chain=[],
            confidence=0.84,
            raw_output={"evidence_status": "ok"},
        ),
    ]
    judge_card = AgentEvidence(
        agent_name="JudgeAgent",
        phase="judgment",
        summary="裁决",
        conclusion="根因已基本收敛",
        evidence_chain=[],
        confidence=0.9,
        raw_output={},
    )

    async def _noop_emit(_: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(orchestrator, "_emit_event", _noop_emit)
    monkeypatch.setattr(orchestrator, "_history_cards_for_state", lambda state, limit=20: history_cards)
    monkeypatch.setattr(orchestrator, "_round_cards_from_state", lambda state: history_cards)
    monkeypatch.setattr(orchestrator, "_recent_judge_card", lambda cards: judge_card)

    result = await orchestrator._graph_round_evaluate(
        {
            "current_round": 2,
            "executed_rounds": 1,
            "supervisor_stop_requested": False,
        }
    )

    assert result["evidence_coverage"]["corroboration_count"] == 0
    assert result["continue_next_round"] is True


def test_inject_followup_objectives_into_commands_enriches_focus():
    """验证 follow-up objectives 会被注入到下一轮专家命令中。"""

    orchestrator = _orchestrator()
    commands = {
        "LogAgent": {
            "target_agent": "LogAgent",
            "task": "分析日志时间线",
            "focus": "围绕 502 错误重建时间线",
            "expected_output": "",
        }
    }

    enriched = orchestrator._inject_followup_objectives_into_commands(
        commands,
        top_k_hypotheses=[
            {"agent_name": "LogAgent", "conclusion": "连接池耗尽导致请求超时", "confidence": 0.88},
            {"agent_name": "CodeAgent", "conclusion": "事务边界过长导致连接占用过高", "confidence": 0.82},
        ],
        round_objectives=["优先验证 Top-1 候选：连接池耗尽导致请求超时"],
        round_gap_summary=["Top-2 根因候选尚未收敛，需要主 Agent 继续追问差异点。"],
    )

    log_command = enriched["LogAgent"]
    assert "优先验证 Top-1 候选" in log_command["focus"]
    assert log_command["followup_gaps"] == ["Top-2 根因候选尚未收敛，需要主 Agent 继续追问差异点。"]
    assert log_command["top_k_hypotheses"][0]["agent_name"] == "LogAgent"
    assert log_command["round_objectives"]
    assert log_command["expected_output"]


@pytest.mark.asyncio
async def test_call_agent_retries_transient_connection_errors(monkeypatch):
    """验证单个Agent调用会对连接抖动做一次重试。"""

    attempts: List[str] = []

    def _fake_run_agent_once(orchestrator, spec, prompt, max_tokens):  # noqa: ANN001, ANN202
        """第一次抛连接错误，第二次返回正常结果。"""
        _ = orchestrator, prompt, max_tokens
        attempts.append(spec.name)
        if len(attempts) == 1:
            raise RuntimeError("Connection error.")
        return AgentInvokeResult(
            content='{"chat_message":"我确认连接池耗尽","final_judgment":{"root_cause":{"summary":"连接池耗尽","category":"db_pool","confidence":0.73},"evidence_chain":[],"fix_recommendation":{"summary":"先限制热点事务","steps":["限制热点 SKU"]},"impact_analysis":{"affected_services":["order-service"],"business_impact":"下单失败"},"risk_assessment":{"risk_level":"high","risk_factors":[]}},"confidence":0.73}',
            invoke_mode="direct",
        )

    monkeypatch.setattr("app.runtime.langgraph.execution.run_agent_once", _fake_run_agent_once)

    class _StubOrchestrator:
        """提供 call_agent 运行所需的最小编排器接口。"""

        session_id = "deb_retry_connection"
        STREAM_CHUNK_SIZE = 160
        STREAM_MAX_CHUNKS = 16
        JUDGE_FALLBACK_SUMMARY = "需要进一步分析"

        def __init__(self):
            self.events: List[Dict[str, Any]] = []
            self._sem = asyncio.Semaphore(1)

        async def _emit_event(self, event: Dict[str, Any]) -> None:
            self.events.append(event)

        def _prompt_template_version(self) -> str:
            return "test"

        def _chat_endpoint(self) -> str:
            return "/v1/chat/completions"

        def _agent_max_tokens(self, agent_name: str) -> int:
            _ = agent_name
            return 256

        def _agent_timeout_plan(self, agent_name: str) -> List[float]:
            _ = agent_name
            return [5.0, 5.0]

        def _remaining_session_budget_seconds(self) -> float:
            return 60.0

        def _agent_queue_timeout(self, agent_name: str) -> float:
            _ = agent_name
            return 5.0

        def _get_llm_semaphore(self) -> asyncio.Semaphore:
            return self._sem

        def _is_rate_limited_error(self, error_text: str) -> bool:
            _ = error_text
            return False

        def _prepare_timeout_retry_input(self, *, spec, prompt: str, max_tokens: int):  # noqa: ANN001
            _ = spec
            return prompt, max_tokens, False

        def _history_cards_snapshot(self):
            return []

        def _infer_reply_target(self, **kwargs):  # noqa: ANN003
            _ = kwargs
            return "ProblemAnalysisAgent"

    orchestrator = _StubOrchestrator()
    turn = await call_agent(
        orchestrator,
        spec=AgentSpec(name="JudgeAgent", role="技术委员会主席", phase="judgment", system_prompt="test"),
        prompt="请给出结论",
        round_number=1,
        loop_round=1,
        history_cards_context=[],
    )

    assert len(attempts) == 2
    assert turn.output_content["final_judgment"]["root_cause"]["summary"] == "连接池耗尽"
    assert turn.output_content["chat_message"] == "我确认连接池耗尽"
    assert any(item.get("type") == "llm_call_retry" for item in orchestrator.events)


@pytest.mark.asyncio
async def test_call_agent_emits_full_prompt_and_response_refs_when_enabled(monkeypatch):
    """验证开启完整日志后，运行时事件会附带完整 prompt/response 引用。"""

    monkeypatch.setattr(settings, "LLM_LOG_FULL_PROMPT", True)
    monkeypatch.setattr(settings, "LLM_LOG_FULL_RESPONSE", True)

    def _fake_run_agent_once(orchestrator, spec, prompt, max_tokens):  # noqa: ANN001, ANN202
        _ = orchestrator, spec, prompt, max_tokens
        return AgentInvokeResult(
            content='{"chat_message":"日志证据确认完毕","conclusion":"连接池耗尽由库存锁等待放大","confidence":0.66}',
            invoke_mode="direct",
        )

    monkeypatch.setattr("app.runtime.langgraph.execution.run_agent_once", _fake_run_agent_once)

    class _StubOrchestrator:
        """提供完整日志测试所需的最小编排器接口。"""

        session_id = "deb_full_log_refs"
        STREAM_CHUNK_SIZE = 160
        STREAM_MAX_CHUNKS = 16
        JUDGE_FALLBACK_SUMMARY = "需要进一步分析"

        def __init__(self):
            self.events: List[Dict[str, Any]] = []
            self._sem = asyncio.Semaphore(1)

        async def _emit_event(self, event: Dict[str, Any]) -> None:
            self.events.append(event)

        def _prompt_template_version(self) -> str:
            return "test"

        def _chat_endpoint(self) -> str:
            return "/v1/chat/completions"

        def _agent_max_tokens(self, agent_name: str) -> int:
            _ = agent_name
            return 256

        def _agent_timeout_plan(self, agent_name: str) -> List[float]:
            _ = agent_name
            return [5.0]

        def _remaining_session_budget_seconds(self) -> float:
            return 60.0

        def _agent_queue_timeout(self, agent_name: str) -> float:
            _ = agent_name
            return 5.0

        def _get_llm_semaphore(self) -> asyncio.Semaphore:
            return self._sem

        def _is_rate_limited_error(self, error_text: str) -> bool:
            _ = error_text
            return False

        def _prepare_timeout_retry_input(self, *, spec, prompt: str, max_tokens: int):  # noqa: ANN001
            _ = spec
            return prompt, max_tokens, False

        def _history_cards_snapshot(self):
            return []

        def _infer_reply_target(self, **kwargs):  # noqa: ANN003
            _ = kwargs
            return "ProblemAnalysisAgent"

    orchestrator = _StubOrchestrator()
    prompt_text = "请根据日志分析连接池耗尽的直接证据链"
    turn = await call_agent(
        orchestrator,
        spec=AgentSpec(name="LogAgent", role="日志分析专家", phase="analysis", system_prompt="你是日志专家"),
        prompt=prompt_text,
        round_number=1,
        loop_round=1,
        history_cards_context=[],
    )

    assert turn.output_content["chat_message"] == "日志证据确认完毕"
    started_event = next(item for item in orchestrator.events if item.get("type") == "llm_call_started")
    response_event = next(item for item in orchestrator.events if item.get("type") == "llm_http_response")

    assert started_event.get("prompt_ref")
    assert started_event.get("system_prompt_ref")
    assert response_event.get("response_ref")

    prompt_payload = get_output_reference(str(started_event.get("prompt_ref")))
    system_payload = get_output_reference(str(started_event.get("system_prompt_ref")))
    response_payload = get_output_reference(str(response_event.get("response_ref")))

    assert prompt_payload and prompt_text in str(prompt_payload.get("content") or "")
    assert system_payload and "你是日志专家" in str(system_payload.get("content") or "")
    assert response_payload and "日志证据确认完毕" in str(response_payload.get("content") or "")


@pytest.mark.asyncio
async def test_call_agent_writes_full_prompt_and_response_to_logger(monkeypatch):
    """验证 runtime logger 会额外写出完整 prompt/response。"""

    monkeypatch.setattr(settings, "LLM_LOG_FULL_PROMPT", True)
    monkeypatch.setattr(settings, "LLM_LOG_FULL_RESPONSE", True)

    captured_logs: List[tuple[str, Dict[str, Any]]] = []

    def _fake_info(event: str, **kwargs: Any) -> None:
        captured_logs.append((event, kwargs))

    monkeypatch.setattr(execution_module.logger, "info", _fake_info)

    class _StubOrchestrator:
        """为 call_agent 提供最小化 orchestrator 依赖。"""

        STREAM_CHUNK_SIZE = 120
        STREAM_MAX_CHUNKS = 24
        JUDGE_FALLBACK_SUMMARY = "结论待补证"

        def __init__(self) -> None:
            self.session_id = "ags_test_runtime_inline"
            self.events: List[Dict[str, Any]] = []
            self._sem = asyncio.Semaphore(1)

        async def _emit_event(self, event: Dict[str, Any]) -> None:
            self.events.append(event)

        def _prompt_template_version(self) -> str:
            return "test"

        def _chat_endpoint(self) -> str:
            return "/v1/chat/completions"

        def _agent_max_tokens(self, agent_name: str) -> int:
            _ = agent_name
            return 256

        def _agent_timeout_plan(self, agent_name: str) -> List[float]:
            _ = agent_name
            return [5.0]

        def _remaining_session_budget_seconds(self) -> float:
            return 60.0

        def _agent_queue_timeout(self, agent_name: str) -> float:
            _ = agent_name
            return 5.0

        def _get_llm_semaphore(self) -> asyncio.Semaphore:
            return self._sem

        def _is_rate_limited_error(self, error_text: str) -> bool:
            _ = error_text
            return False

        def _prepare_timeout_retry_input(self, *, spec, prompt: str, max_tokens: int):  # noqa: ANN001
            _ = spec
            return prompt, max_tokens, False

        def _history_cards_snapshot(self):
            return []

        def _infer_reply_target(self, **kwargs):  # noqa: ANN003
            _ = kwargs
            return "ProblemAnalysisAgent"

    monkeypatch.setattr(
        execution_module,
        "run_agent_once",
        lambda orchestrator, spec, prompt, max_tokens: AgentInvokeResult(
            content='{"chat_message":"日志确认完成","analysis":"已定位到连接池耗尽","conclusion":"连接池耗尽由库存锁等待放大","confidence":0.62}',
            invoke_mode="direct",
        ),
    )

    orchestrator = _StubOrchestrator()
    prompt_text = "请结合日志定位连接池耗尽与库存锁等待的关系"
    await call_agent(
        orchestrator,
        spec=AgentSpec(name="LogAgent", role="日志分析专家", phase="analysis", system_prompt="你是日志专家"),
        prompt=prompt_text,
        round_number=1,
        loop_round=1,
        history_cards_context=[],
    )

    prompt_log = next(item for item in captured_logs if item[0] == "runtime_agent_llm_prompt_full")
    response_log = next(item for item in captured_logs if item[0] == "runtime_agent_llm_response_full")

    assert prompt_text in str(prompt_log[1].get("prompt_full") or "")
    assert "你是日志专家" in str(prompt_log[1].get("system_prompt_full") or "")
    assert "连接池耗尽由库存锁等待放大" in str(response_log[1].get("response_full") or "")


@pytest.mark.asyncio
async def test_call_agent_invoke_timeout_is_not_misclassified_as_queue_timeout(monkeypatch):
    """验证模型推理超时不会被错误记成队列超时。"""

    import time

    def _slow_run_agent_once(orchestrator, spec, prompt, max_tokens):  # noqa: ANN001, ANN202
        _ = orchestrator, spec, prompt, max_tokens
        time.sleep(0.05)
        return AgentInvokeResult(
            content='{"chat_message":"slow","conclusion":"slow","confidence":0.1}',
            invoke_mode="direct",
        )

    monkeypatch.setattr("app.runtime.langgraph.execution.run_agent_once", _slow_run_agent_once)

    class _StubOrchestrator:
        session_id = "deb_invoke_timeout"
        STREAM_CHUNK_SIZE = 120
        STREAM_MAX_CHUNKS = 12
        JUDGE_FALLBACK_SUMMARY = "需要进一步分析"

        def __init__(self):
            self.events: List[Dict[str, Any]] = []
            self._sem = asyncio.Semaphore(1)
            self._execution_mode_name = "background"

        async def _emit_event(self, event: Dict[str, Any]) -> None:
            self.events.append(event)

        def _prompt_template_version(self) -> str:
            return "test"

        def _chat_endpoint(self) -> str:
            return "/v1/chat/completions"

        def _agent_max_tokens(self, agent_name: str) -> int:
            _ = agent_name
            return 128

        def _agent_timeout_plan(self, agent_name: str) -> List[float]:
            _ = agent_name
            return [0.01]

        def _remaining_session_budget_seconds(self) -> float:
            return 60.0

        def _agent_queue_timeout(self, agent_name: str) -> float:
            _ = agent_name
            return 0.5

        def _get_llm_semaphore(self) -> asyncio.Semaphore:
            return self._sem

        def _is_rate_limited_error(self, error_text: str) -> bool:
            _ = error_text
            return False

        def _prepare_timeout_retry_input(self, *, spec, prompt: str, max_tokens: int):  # noqa: ANN001
            _ = spec
            return prompt, max_tokens, False

        def _history_cards_snapshot(self):
            return []

        def _infer_reply_target(self, **kwargs):  # noqa: ANN003
            _ = kwargs
            return "ProblemAnalysisAgent"

    orchestrator = _StubOrchestrator()

    with pytest.raises(RuntimeError, match="LogAgent 调用失败"):
        await call_agent(
            orchestrator,
            spec=AgentSpec(name="LogAgent", role="日志分析专家", phase="analysis", system_prompt="你是日志专家"),
            prompt="请分析",
            round_number=1,
            loop_round=1,
            history_cards_context=[],
        )

    event_types = [str(item.get("type") or "") for item in orchestrator.events]
    assert "llm_call_timeout" in event_types
    assert "llm_queue_timeout" not in event_types
