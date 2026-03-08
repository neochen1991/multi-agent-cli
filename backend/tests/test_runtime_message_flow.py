"""test运行时消息flow相关测试。"""

import asyncio

from langchain_core.messages import AIMessage

from app.runtime.langgraph.phase_executor import PhaseExecutor
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.langgraph.state import AgentSpec, DebateTurn
from app.runtime.messages import AgentEvidence


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    """为测试场景提供orchestrator辅助逻辑。"""
    
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


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


def test_analysis_batch_limit_reserves_slot_for_settlement_agents():
    """验证分析batchlimitreservesslotforsettlementAgent。"""
    
    orchestrator = _orchestrator()
    orchestrator._llm_semaphore_limit = 3

    assert orchestrator._analysis_batch_limit(collaboration=False) == 2
    assert orchestrator._analysis_batch_limit(collaboration=True) == 2

    orchestrator._llm_semaphore_limit = 2
    assert orchestrator._analysis_batch_limit(collaboration=False) == 1


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
