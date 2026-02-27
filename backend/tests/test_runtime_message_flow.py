"""Tests for runtime message dedupe and dialogue-driven peer extraction."""

from langchain_core.messages import AIMessage

from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.langgraph.state import AgentSpec
from app.runtime.messages import AgentEvidence


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


def test_dedupe_new_messages_skips_same_signature():
    orchestrator = _orchestrator()
    existing = [AIMessage(content="同意：先看日志证据", name="DomainAgent")]
    incoming = [AIMessage(content="同意：先看日志证据", name="DomainAgent")]

    deduped = orchestrator._dedupe_new_messages(existing_messages=existing, new_messages=incoming)

    assert deduped == []


def test_build_peer_driven_prompt_prefers_dialogue_items():
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


def test_commander_prompt_can_use_existing_agent_outputs():
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
