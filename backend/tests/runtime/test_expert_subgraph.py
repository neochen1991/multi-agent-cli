"""关键专家多步调查子图的运行时测试。"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from app.runtime.langgraph.execution import AgentInvokeResult, call_agent
from app.runtime.langgraph.state import AgentSpec


class _StubOrchestrator:
    """为多步调查测试提供最小编排器依赖。"""

    session_id = "debate_expert_subgraph"
    STREAM_CHUNK_SIZE = 160
    STREAM_MAX_CHUNKS = 16
    JUDGE_FALLBACK_SUMMARY = "需要进一步分析"
    analysis_depth_mode = "standard"

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self._sem = asyncio.Semaphore(1)

    async def _emit_event(self, event: Dict[str, Any]) -> None:
        self.events.append(dict(event))

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


@pytest.mark.asyncio
async def test_call_agent_runs_multistep_investigation_for_key_expert(monkeypatch):
    """关键证据专家应先产出调查计划，再给出最终结论。"""

    prompts: List[str] = []

    def _fake_run_agent_once(orchestrator, spec, prompt, max_tokens):  # noqa: ANN001, ANN202
        _ = orchestrator, max_tokens
        prompts.append(str(prompt))
        if spec.name == "CodeAgent" and "多步调查计划" in str(prompt):
            return AgentInvokeResult(
                content='{"hypotheses":["连接池释放延迟"],"checks":["核对事务边界","核对DAO调用耗时"],"next_focus":"优先检查事务与连接释放路径"}',
                invoke_mode="direct",
            )
        return AgentInvokeResult(
            content='{"chat_message":"我先按计划检查了事务与连接释放路径。","conclusion":"订单创建链路存在长事务，导致连接释放延迟并放大连接池耗尽。","confidence":0.83,"evidence_chain":["事务边界覆盖远程调用","DAO获取连接后释放滞后"]}',
            invoke_mode="direct",
        )

    monkeypatch.setattr("app.runtime.langgraph.execution.run_agent_once", _fake_run_agent_once)

    orchestrator = _StubOrchestrator()
    turn = await call_agent(
        orchestrator,
        spec=AgentSpec(name="CodeAgent", role="代码分析专家", phase="analysis", system_prompt="你是代码专家"),
        prompt="请检查订单创建路径中的连接池异常。",
        round_number=1,
        loop_round=1,
        history_cards_context=[],
        execution_context={
            "tool_context": {"name": "code_bundle", "summary": "已预取 controller/service/dao 命中结果"},
            "focused_context": {
                "problem_entrypoint": {"interface": "OrderController#createOrder"},
                "method_call_chain": ["OrderController#createOrder", "OrderService#create", "OrderDao#insert"],
            },
        },
    )

    assert len(prompts) == 2
    assert "多步调查计划" in prompts[0]
    assert "调查备忘录" in prompts[1]
    assert "连接池释放延迟" in prompts[1]
    assert turn.output_content["conclusion"] == "订单创建链路存在长事务，导致连接释放延迟并放大连接池耗尽。"

    event_types = [str(item.get("type")) for item in orchestrator.events]
    assert "expert_investigation_started" in event_types
    assert "expert_investigation_step_completed" in event_types
    assert "expert_investigation_completed" in event_types


@pytest.mark.asyncio
async def test_metrics_agent_runs_multistep_investigation_in_standard_mode(monkeypatch):
    """MetricsAgent 在 standard 模式下也应进入计划 -> 综合闭环。"""

    prompts: List[str] = []

    def _fake_run_agent_once(orchestrator, spec, prompt, max_tokens):  # noqa: ANN001, ANN202
        _ = orchestrator, max_tokens
        prompts.append(str(prompt))
        if spec.name == "MetricsAgent" and "多步调查计划" in str(prompt):
            return AgentInvokeResult(
                content='{"hypotheses":["上游重试放大 RT"],"checks":["核对 RT 与 error rate 时间线","核对 DB 指标是否平稳"],"next_focus":"优先确认调用链传播顺序"}',
                invoke_mode="direct",
            )
        return AgentInvokeResult(
            content='{"chat_message":"我先按计划比对了 RT、错误率和数据库指标。","conclusion":"支付确认超时由上游 RiskService 重试放大，数据库指标保持平稳，不是主因。","confidence":0.79,"evidence_chain":["payment RT 逐次抬升","Risk timeout timeline","DB CPU/slow SQL 平稳"]}',
            invoke_mode="direct",
        )

    monkeypatch.setattr("app.runtime.langgraph.execution.run_agent_once", _fake_run_agent_once)

    orchestrator = _StubOrchestrator()
    turn = await call_agent(
        orchestrator,
        spec=AgentSpec(name="MetricsAgent", role="指标分析专家", phase="analysis", system_prompt="你是指标专家"),
        prompt="请分析支付确认链路的指标传播顺序。",
        round_number=1,
        loop_round=1,
        history_cards_context=[],
        execution_context={
            "tool_context": {"name": "metrics_bundle", "summary": "已预取 RT/error rate/DB CPU 时间线"},
            "focused_context": {
                "metric_window": {"service": "payment-service", "window": "10:08-10:12"},
                "causal_timeline": ["Risk timeout spike", "payment RT increase", "DB CPU stable"],
            },
        },
    )

    assert len(prompts) == 2
    assert "多步调查计划" in prompts[0]
    assert "调查备忘录" in prompts[1]
    assert "上游重试放大 RT" in prompts[1]
    assert "数据库指标保持平稳" in turn.output_content["conclusion"]


@pytest.mark.asyncio
async def test_metrics_agent_runs_reflection_step_in_deep_mode(monkeypatch):
    """deep 模式下 MetricsAgent 应额外执行一次反证复核。"""

    prompts: List[str] = []

    def _fake_run_agent_once(orchestrator, spec, prompt, max_tokens):  # noqa: ANN001, ANN202
        _ = orchestrator, max_tokens
        prompts.append(str(prompt))
        if "多步调查计划" in str(prompt):
            return AgentInvokeResult(
                content='{"hypotheses":["上游重试耗尽预算"],"checks":["核对 timeout timeline"],"next_focus":"确认 DB 是否平稳"}',
                invoke_mode="direct",
            )
        if "反证复核" in str(prompt):
            return AgentInvokeResult(
                content='{"contradictions":["数据库 CPU 低于 20%"],"missing_checks":["补网关 p95 时间线"],"revised_focus":"优先保持上游超时假设"}',
                invoke_mode="direct",
            )
        return AgentInvokeResult(
            content='{"chat_message":"我补过反证后仍维持原结论。","conclusion":"主因是上游重试耗尽预算，数据库仅为被排除项。","confidence":0.81,"evidence_chain":["Risk timeout timeline","DB CPU 18%","slow SQL 0"]}',
            invoke_mode="direct",
        )

    monkeypatch.setattr("app.runtime.langgraph.execution.run_agent_once", _fake_run_agent_once)

    orchestrator = _StubOrchestrator()
    orchestrator.analysis_depth_mode = "deep"
    turn = await call_agent(
        orchestrator,
        spec=AgentSpec(name="MetricsAgent", role="指标分析专家", phase="analysis", system_prompt="你是指标专家"),
        prompt="请分析支付超时的指标传播链。",
        round_number=1,
        loop_round=1,
        history_cards_context=[],
        execution_context={
            "tool_context": {"name": "metrics_bundle", "summary": "已预取 payment/risk/db 三段指标"},
            "focused_context": {"causal_timeline": ["Risk timeout spike", "payment RT increase", "DB stable"]},
        },
    )

    assert len(prompts) == 3
    assert "多步调查计划" in prompts[0]
    assert "反证复核" in prompts[1]
    assert "调查备忘录" in prompts[2]
    assert turn.output_content["confidence"] == 0.81
