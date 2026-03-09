"""
LangGraph 运行时里的 Agent 调用执行层。

这个模块专门承接“真正去调模型”的重逻辑，目的是把 orchestrator 主类里的职责拆开：
1. orchestrator 负责状态机、路由、审计和会话生命周期。
2. execution 模块负责 prompt 调用、重试、超时、结构化解析和流式事件。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, Dict, Optional

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.llm_client import LLMClient
from app.runtime.langgraph.parsers import normalize_agent_output
from app.runtime.langgraph.output_truncation import (
    save_output_reference,
    truncate_payload,
    truncate_text,
)
from app.runtime.langgraph.state import AgentSpec, DebateTurn
from app.runtime.langgraph.schemas import get_schema_for_agent

logger = structlog.get_logger()


def _full_text_log_refs(
    *,
    session_id: str,
    agent_name: str,
    phase: str,
    round_number: int,
    loop_round: int,
    prompt: str = "",
    response: str = "",
    system_prompt: str = "",
) -> Dict[str, str]:
    """按调试开关把完整 prompt/response 落盘，并返回事件可用的 ref。"""
    refs: Dict[str, str] = {}
    metadata = {
        "agent_name": agent_name,
        "phase": phase,
        "round_number": round_number,
        "loop_round": loop_round,
    }
    if settings.LLM_LOG_FULL_PROMPT:
        if system_prompt:
            refs["system_prompt_ref"] = save_output_reference(
                content=system_prompt,
                session_id=session_id,
                category="llm_system_prompt",
                metadata=metadata,
            )
        if prompt:
            refs["prompt_ref"] = save_output_reference(
                content=prompt,
                session_id=session_id,
                category="llm_prompt",
                metadata=metadata,
            )
    if settings.LLM_LOG_FULL_RESPONSE and response:
        refs["response_ref"] = save_output_reference(
            content=response,
            session_id=session_id,
            category="llm_response",
            metadata=metadata,
        )
    return refs


def _build_full_log_fields(
    *,
    prompt: str = "",
    system_prompt: str = "",
    response: str = "",
) -> Dict[str, str]:
    """按调试开关返回应直接写入 backend.log 的完整 LLM 文本字段。"""
    payload: Dict[str, str] = {}
    if settings.LLM_LOG_FULL_PROMPT:
        if system_prompt:
            payload["system_prompt_full"] = system_prompt
        if prompt:
            payload["prompt_full"] = prompt
    if settings.LLM_LOG_FULL_RESPONSE and response:
        payload["response_full"] = response
    return payload


@dataclass
class AgentInvokeResult:
    """封装单次模型调用的原始文本结果和调用模式。"""
    content: str
    invoke_mode: str


class RetryableAgentTimeoutError(RuntimeError):
    """Retry marker for timeout-like transient failures."""


class FatalLLMError(RuntimeError):
    """Non-recoverable LLM error that should fail the session immediately."""


def _is_transient_llm_error(error_text: str) -> bool:
    """识别可短暂重试的连接抖动类 LLM 异常。"""
    lowered = str(error_text or "").strip().lower()
    if not lowered:
        return False
    transient_markers = (
        "connection error",
        "connection reset",
        "server disconnected",
        "temporarily unavailable",
        "remoteprotocolerror",
        "connecterror",
        "readerror",
        "broken pipe",
    )
    return any(marker in lowered for marker in transient_markers)


async def emit_stream_deltas(
    orchestrator: Any,
    *,
    spec: AgentSpec,
    raw_content: str,
    loop_round: int,
    round_number: int,
) -> None:
    """
    把完整 LLM 输出切分成多个流式片段事件发给前端。

    这里不是实时 token streaming，而是把一次完整输出按固定大小切块，
    用来在前端模拟逐步展开的对话感，同时控制事件数量上限。
    """
    content = (raw_content or "").strip()
    if not content:
        return
    chunks = [
        content[i : i + orchestrator.STREAM_CHUNK_SIZE]
        for i in range(0, len(content), orchestrator.STREAM_CHUNK_SIZE)
    ]
    truncated = False
    if len(chunks) > orchestrator.STREAM_MAX_CHUNKS:
        chunks = chunks[: orchestrator.STREAM_MAX_CHUNKS]
        truncated = True
    stream_id = f"{orchestrator.session_id}:{spec.name}:{round_number}"
    for index, chunk in enumerate(chunks, start=1):
        await orchestrator._emit_event(
            {
                "type": "llm_stream_delta",
                "phase": spec.phase,
                "agent_name": spec.name,
                "model": settings.llm_model,
                "session_id": orchestrator.session_id,
                "stream_id": stream_id,
                "loop_round": loop_round,
                "round_number": round_number,
                "chunk_index": index,
                "chunk_total": len(chunks),
                "delta": chunk,
                "truncated": truncated,
            }
        )


def run_agent_once(orchestrator: Any, spec: AgentSpec, prompt: str, max_tokens: int) -> AgentInvokeResult:
    """
    以最直接模式调用一次大模型，不做结构化 schema 约束。

    这个入口主要用于：
    - 普通自然语言输出
    - 结构化模式失败后的 fallback
    """
    # direct 模式只负责“最朴素的一次调用”，不做结构化 schema 约束。
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 未配置，无法调用模型")
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.LLM_API_KEY,
        base_url=orchestrator._base_url_for_llm(),
        temperature=0.15,
        timeout=orchestrator._agent_http_timeout(spec.name),
        max_retries=max(0, int(settings.LLM_MAX_RETRIES)),
        max_tokens=max(128, int(max_tokens or 256)),
        model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
    )
    reply = llm.invoke(
        [
            SystemMessage(content=spec.system_prompt or "你是严谨的 SRE 分析助手。"),
            HumanMessage(content=prompt),
        ]
    )
    return AgentInvokeResult(
        content=LLMClient._extract_reply_text(reply, agent_name=spec.name),
        invoke_mode="direct",
    )


def run_agent_with_structured_output(
    orchestrator: Any,
    spec: AgentSpec,
    prompt: str,
    max_tokens: int,
) -> tuple[Dict[str, Any], str]:
    """
    用 Pydantic schema 驱动结构化输出调用。

    优先尝试模型原生 structured output；如果失败，再回退到普通文本调用。
    这样做的目的是尽量保证关键 Agent 输出可解析，但不因为 schema 失败直接丢掉一次调用结果。
    """
    # structured output 是首选路径，因为它能显著降低解析漂移。
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 未配置，无法调用模型")

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.LLM_API_KEY,
        base_url=orchestrator._base_url_for_llm(),
        temperature=0.15,
        timeout=orchestrator._agent_http_timeout(spec.name),
        max_retries=max(0, int(settings.LLM_MAX_RETRIES)),
        max_tokens=max(128, int(max_tokens or 256)),
        model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
    )

    # 为不同 Agent 选择对应 schema，避免所有 Agent 共用一个过宽结构。
    schema = get_schema_for_agent(spec.name)

    try:
        # 优先走原生 structured output，减少后处理解析误差。
        structured_llm = llm.with_structured_output(schema)
        messages = [
            SystemMessage(content=spec.system_prompt or "你是严谨的 SRE 分析助手。"),
            HumanMessage(content=prompt),
        ]
        result = structured_llm.invoke(messages)

        if hasattr(result, "model_dump"):
            output = result.model_dump()
        elif isinstance(result, dict):
            output = result
        else:
            output = {"raw_content": str(result)}

        logger.info(
            "structured_output_success",
            agent_name=spec.name,
            schema=schema.__name__,
        )
        return output, "structured"

    except Exception as e:
        logger.warning(
            "structured_output_fallback",
            agent_name=spec.name,
            error=str(e)[:200],
            fallback="manual_parsing",
        )

        # schema 失败时退回普通文本模式，至少保留可读内容，后续再人工/程序解析。
        reply = llm.invoke([
            SystemMessage(content=spec.system_prompt or "你是严谨的 SRE 分析助手。"),
            HumanMessage(content=prompt),
        ])
        raw_content = LLMClient._extract_reply_text(reply, agent_name=spec.name)
        return {"raw_content": raw_content}, "direct_fallback"


async def call_agent(
    orchestrator: Any,
    *,
    spec: AgentSpec,
    prompt: str,
    round_number: int,
    loop_round: int,
    history_cards_context: Optional[list[Any]] = None,
) -> DebateTurn:
    """
    执行一次完整 Agent 调用，并把模型输出归一化成 DebateTurn。

    这个函数是执行层主入口，负责串起：
    - prompt 调用
    - 结构化输出/普通输出双模式
    - 超时和重试策略
    - 审计事件
    - turn 归一化
    """
    # call_agent 是 execution 层主入口，负责把一次模型调用最终落成标准 DebateTurn。
    started_at = datetime.utcnow()
    model_name = settings.llm_model
    endpoint = orchestrator._chat_endpoint()
    agent_max_tokens = orchestrator._agent_max_tokens(spec.name)
    attempt_prompt = prompt
    attempt_max_tokens = agent_max_tokens
    timeout_plan = orchestrator._agent_timeout_plan(spec.name)
    max_attempts = max(1, len(timeout_plan))
    prompt_template_version = (
        str(orchestrator._prompt_template_version())
        if hasattr(orchestrator, "_prompt_template_version")
        else "unknown"
    )
    event_common = {
        "phase": spec.phase,
        "agent_name": spec.name,
        "session_id": orchestrator.session_id,
        "model": model_name,
        "loop_round": loop_round,
        "round_number": round_number,
        "prompt_template_version": prompt_template_version,
    }
    prompt_refs = _full_text_log_refs(
        session_id=str(orchestrator.session_id or ""),
        agent_name=spec.name,
        phase=spec.phase,
        round_number=round_number,
        loop_round=loop_round,
        prompt=prompt,
        system_prompt=str(spec.system_prompt or ""),
    )

    # 在真正请求模型前先写开始事件，前端和审计系统才能看到完整调用链。
    await orchestrator._emit_event(
        {
            "type": "llm_call_started",
            **event_common,
            "prompt_preview": prompt[:1200],
            "prompt_length": len(prompt),
            "max_tokens": agent_max_tokens,
            "timeout_plan": timeout_plan,
            "max_attempts": max_attempts,
            **prompt_refs,
        }
    )
    await orchestrator._emit_event(
        {
            "type": "llm_request_started",
            **event_common,
            "prompt_preview": prompt[:1200],
            "prompt_length": len(prompt),
            "max_tokens": agent_max_tokens,
            "timeout_plan": timeout_plan,
            "max_attempts": max_attempts,
            **prompt_refs,
        }
    )
    await orchestrator._emit_event(
        {
            "type": "llm_http_request",
            **event_common,
            "endpoint": endpoint,
            "request_payload": {
                "model": model_name,
                "max_tokens": agent_max_tokens,
                "message_count": 2,
                "prompt_length": len(prompt),
                "prompt_preview": prompt[:1200],
                **prompt_refs,
            },
            **prompt_refs,
        }
    )
    logger.info(
        "runtime_agent_llm_scheduled",
        session_id=orchestrator.session_id,
        agent_name=spec.name,
        phase=spec.phase,
        loop_round=loop_round,
        round_number=round_number,
        timeout_plan=timeout_plan,
        max_tokens=attempt_max_tokens,
        prompt_length=len(attempt_prompt),
        prompt_ref=prompt_refs.get("prompt_ref"),
        system_prompt_ref=prompt_refs.get("system_prompt_ref"),
        full_prompt_logging=bool(settings.LLM_LOG_FULL_PROMPT),
    )
    if settings.LLM_LOG_FULL_PROMPT:
        logger.info(
            "runtime_agent_llm_prompt_full",
            session_id=orchestrator.session_id,
            agent_name=spec.name,
            phase=spec.phase,
            loop_round=loop_round,
            round_number=round_number,
            prompt_ref=prompt_refs.get("prompt_ref"),
            system_prompt_ref=prompt_refs.get("system_prompt_ref"),
            **_build_full_log_fields(
                prompt=attempt_prompt,
                system_prompt=str(spec.system_prompt or ""),
            ),
        )
    retrying = AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=2.0),
        retry=retry_if_exception_type(RetryableAgentTimeoutError),
        reraise=True,
    )

    try:
        # execution 层的重试只覆盖“超时/连接抖动类短暂故障”，不覆盖认证/配额等致命错误。
        async for attempt in retrying:
            attempt_idx = int(attempt.retry_state.attempt_number or 1)
            attempt_timeout = timeout_plan[min(attempt_idx - 1, len(timeout_plan) - 1)]
            session_budget = orchestrator._remaining_session_budget_seconds()
            if session_budget is not None:
                # Keep a small buffer to avoid consuming the whole session budget in one call.
                attempt_timeout = min(float(attempt_timeout), max(1.0, float(session_budget) - 1.0))
            started_clock = perf_counter()
            with attempt:
                try:
                    if session_budget is not None and session_budget <= 1.0:
                        await orchestrator._emit_event(
                            {
                                "type": "session_budget_exhausted",
                                **event_common,
                                "attempt": attempt_idx,
                                "max_attempts": max_attempts,
                                "remaining_seconds": round(float(session_budget), 3),
                            }
                        )
                        raise asyncio.TimeoutError("session timeout budget exhausted")

                    # 先争抢 LLM semaphore。这里的 queue timeout 衡量的是“排队等模型”的耗时，
                    # 和真正的 HTTP/模型推理超时是两套不同门限。
                    queue_timeout = float(orchestrator._agent_queue_timeout(spec.name))
                    if session_budget is not None:
                        queue_timeout = min(queue_timeout, max(0.5, float(session_budget)))
                    queue_started = perf_counter()
                    semaphore = orchestrator._get_llm_semaphore()
                    acquired = False
                    try:
                        await asyncio.wait_for(semaphore.acquire(), timeout=queue_timeout)
                        acquired = True
                    except asyncio.TimeoutError as queue_exc:
                        queue_wait_ms = round((perf_counter() - queue_started) * 1000, 2)
                        await orchestrator._emit_event(
                            {
                                "type": "llm_queue_timeout",
                                **event_common,
                                "attempt": attempt_idx,
                                "max_attempts": max_attempts,
                                "queue_timeout_seconds": queue_timeout,
                                "queue_wait_ms": queue_wait_ms,
                            }
                        )
                        raise RetryableAgentTimeoutError(
                            f"llm queue timeout after {queue_timeout:.1f}s"
                        ) from queue_exc
                    queue_wait_ms = round((perf_counter() - queue_started) * 1000, 2)
                    logger.info(
                        "runtime_agent_llm_started",
                        session_id=orchestrator.session_id,
                        agent_name=spec.name,
                        phase=spec.phase,
                        loop_round=loop_round,
                        round_number=round_number,
                        attempt=attempt_idx,
                        max_attempts=max_attempts,
                        timeout_seconds=attempt_timeout,
                        queue_timeout_seconds=queue_timeout,
                        queue_wait_ms=queue_wait_ms,
                        session_budget_seconds=(
                            round(float(session_budget), 3)
                            if session_budget is not None
                            else None
                        ),
                    )
                    try:
                        invoke_result = await asyncio.wait_for(
                            asyncio.to_thread(
                                run_agent_once,
                                orchestrator,
                                spec,
                                attempt_prompt,
                                attempt_max_tokens,
                            ),
                            timeout=attempt_timeout,
                        )
                    except asyncio.TimeoutError as invoke_exc:
                        raise RetryableAgentTimeoutError(
                            f"llm invoke timeout after {attempt_timeout:.1f}s"
                        ) from invoke_exc
                    finally:
                        if acquired:
                            semaphore.release()
                    # 从这里开始，说明本次调用已经真正拿到模型结果，
                    # 后续重点转向“结果截断、归一化、事件落盘和 turn 构造”。
                    raw_content = str(getattr(invoke_result, "content", "") or "")
                    raw_content = truncate_text(
                        raw_content,
                        max_chars=9000,
                        session_id=str(orchestrator.session_id or ""),
                        category="llm_raw_content",
                        metadata={
                            "agent_name": spec.name,
                            "phase": spec.phase,
                            "round_number": round_number,
                            "loop_round": loop_round,
                        },
                    )
                    invoke_mode = str(getattr(invoke_result, "invoke_mode", "") or "direct")
                    response_refs = _full_text_log_refs(
                        session_id=str(orchestrator.session_id or ""),
                        agent_name=spec.name,
                        phase=spec.phase,
                        round_number=round_number,
                        loop_round=loop_round,
                        response=raw_content,
                    )
                    await orchestrator._emit_event(
                        {
                            "type": "llm_invoke_path",
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "session_id": orchestrator.session_id,
                            "model": model_name,
                            "invoke_mode": invoke_mode,
                            "execution_path": "chat_openai_direct",
                            "tool_count": len(tuple(spec.tools or ())),
                        }
                    )
                    latency_ms = round((perf_counter() - started_clock) * 1000, 2)
                    payload = normalize_agent_output(
                        spec.name,
                        raw_content,
                        judge_fallback_summary=orchestrator.JUDGE_FALLBACK_SUMMARY,
                    )
                    payload = truncate_payload(
                        payload,
                        max_chars=2600,
                        session_id=str(orchestrator.session_id or ""),
                        category="agent_output_payload",
                        metadata={
                            "agent_name": spec.name,
                            "phase": spec.phase,
                            "round_number": round_number,
                            "loop_round": loop_round,
                        },
                    )
                    if spec.name == "JudgeAgent":
                        # Judge 的 fallback summary 需要单独打点，后续治理和前端
                        # 会据此判断“这次裁决是否只是占位结论”。
                        final_judgment = payload.get("final_judgment")
                        root_cause = (
                            final_judgment.get("root_cause")
                            if isinstance(final_judgment, dict)
                            else {}
                        )
                        root_summary = (
                            str(root_cause.get("summary") or "").strip()
                            if isinstance(root_cause, dict)
                            else ""
                        )
                        if root_summary == orchestrator.JUDGE_FALLBACK_SUMMARY:
                            await orchestrator._emit_event(
                                {
                                    "type": "judge_output_fallback_applied",
                                    "phase": spec.phase,
                                    "agent_name": spec.name,
                                    "session_id": orchestrator.session_id,
                                    "model": model_name,
                                    "reason": "judge_output_parse_incomplete",
                                    "raw_preview": raw_content[:800],
                                }
                            )
                    await emit_stream_deltas(
                        orchestrator,
                        spec=spec,
                        raw_content=raw_content,
                        loop_round=loop_round,
                        round_number=round_number,
                    )

                    # 到这里才把模型输出整理成标准 DebateTurn，交给上层并入 history_cards。
                    completed_at = datetime.utcnow()
                    turn = DebateTurn(
                        round_number=round_number,
                        phase=spec.phase,
                        agent_name=spec.name,
                        agent_role=spec.role,
                        model={"name": model_name},
                        input_message=attempt_prompt,
                        output_content=payload,
                        confidence=float(payload.get("confidence", 0.0) or 0.0),
                        started_at=started_at,
                        completed_at=completed_at,
                    )

                    await orchestrator._emit_event(
                        {
                            "type": "llm_http_response",
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "session_id": orchestrator.session_id,
                            "model": model_name,
                            "endpoint": endpoint,
                            "status_code": 200,
                            "response_payload": {
                                "content_preview": raw_content[:1200],
                                "content_length": len(raw_content),
                                **response_refs,
                            },
                            "latency_ms": latency_ms,
                            "invoke_mode": invoke_mode,
                            **response_refs,
                        }
                    )
                    await orchestrator._emit_event(
                        {
                            "type": "agent_round",
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "agent_role": spec.role,
                            "loop_round": loop_round,
                            "round_number": round_number,
                            "confidence": turn.confidence,
                            "latency_ms": latency_ms,
                            "output_preview": str(payload)[:1200],
                            "output_json": payload,
                            "started_at": started_at.isoformat(),
                            "completed_at": completed_at.isoformat(),
                            "session_id": orchestrator.session_id,
                            "invoke_mode": invoke_mode,
                        }
                    )
                    chat_message = str(payload.get("chat_message") or "").strip()
                    if chat_message:
                        # chat_message 是给前端可读对话流看的，不等于结构化结论本身。
                        history_cards = list(history_cards_context or orchestrator._history_cards_snapshot())
                        await orchestrator._emit_event(
                            {
                                "type": "agent_chat_message",
                                "phase": spec.phase,
                                "agent_name": spec.name,
                                "agent_role": spec.role,
                                "model": model_name,
                                "session_id": orchestrator.session_id,
                                "loop_round": loop_round,
                                "round_number": round_number,
                                "message": chat_message[:1200],
                                "confidence": turn.confidence,
                                "conclusion": str(payload.get("conclusion") or "")[:220],
                                "reply_to": orchestrator._infer_reply_target(
                                    spec_name=spec.name,
                                    history_cards=[c for c in history_cards if c.agent_name != spec.name],
                                ),
                            }
                        )
                    await orchestrator._emit_event(
                        {
                            "type": "llm_call_completed",
                            **event_common,
                            "response_preview": raw_content[:1200],
                            "response_length": len(raw_content),
                            "latency_ms": latency_ms,
                            "invoke_mode": invoke_mode,
                            "attempt": attempt_idx,
                            "max_attempts": max_attempts,
                            **response_refs,
                        }
                    )
                    await orchestrator._emit_event(
                        {
                            "type": "llm_request_completed",
                            **event_common,
                            "response_preview": raw_content[:1200],
                            "response_length": len(raw_content),
                            "latency_ms": latency_ms,
                            "invoke_mode": invoke_mode,
                            "attempt": attempt_idx,
                            "max_attempts": max_attempts,
                            **response_refs,
                        }
                    )
                    logger.info(
                        "runtime_agent_llm_completed",
                        session_id=orchestrator.session_id,
                        agent_name=spec.name,
                        phase=spec.phase,
                        loop_round=loop_round,
                        round_number=round_number,
                        attempt=attempt_idx,
                        latency_ms=latency_ms,
                        response_length=len(raw_content or ""),
                        confidence=float(payload.get("confidence", 0.0) or 0.0),
                        invoke_mode=invoke_mode,
                        response_ref=response_refs.get("response_ref"),
                        full_response_logging=bool(settings.LLM_LOG_FULL_RESPONSE),
                    )
                    if settings.LLM_LOG_FULL_RESPONSE:
                        logger.info(
                            "runtime_agent_llm_response_full",
                            session_id=orchestrator.session_id,
                            agent_name=spec.name,
                            phase=spec.phase,
                            loop_round=loop_round,
                            round_number=round_number,
                            attempt=attempt_idx,
                            response_ref=response_refs.get("response_ref"),
                            **_build_full_log_fields(response=raw_content),
                        )
                    return turn
                except Exception as exc:
                    # 错误分流逻辑：
                    # 1. 致命错误直接抛 FatalLLMError
                    # 2. 超时/连接抖动类错误允许按 timeout_plan 做重试
                    # 3. 其他错误由上层决定是否转 fallback turn
                    latency_ms = round((perf_counter() - started_clock) * 1000, 2)
                    error_text = str(exc).strip() or exc.__class__.__name__
                    is_timeout = isinstance(exc, asyncio.TimeoutError) or "timeout" in error_text.lower()
                    is_transient = _is_transient_llm_error(error_text)
                    if settings.LLM_FAILFAST_ON_RATE_LIMIT and orchestrator._is_rate_limited_error(error_text):
                        error_text = f"LLM_RATE_LIMITED: {error_text}"
                    lowered_error = error_text.lower()
                    fatal_markers = (
                        "invalidsubscription",
                        "invalid subscription",
                        "invalidapikey",
                        "invalid api key",
                        "authentication",
                        "unauthorized",
                        "llm_rate_limited",
                    )
                    if any(marker in lowered_error for marker in fatal_markers):
                        logger.error(
                            "runtime_agent_llm_fatal",
                            session_id=orchestrator.session_id,
                            agent_name=spec.name,
                            phase=spec.phase,
                            loop_round=loop_round,
                            round_number=round_number,
                            attempt=attempt_idx,
                            max_attempts=max_attempts,
                            latency_ms=latency_ms,
                            error=error_text,
                        )
                        await orchestrator._emit_event(
                            {
                                "type": "llm_call_failed",
                                **event_common,
                                "error": error_text,
                                "latency_ms": latency_ms,
                                "timeout_seconds": attempt_timeout,
                                "attempt": attempt_idx,
                                "max_attempts": max_attempts,
                                "fatal": True,
                            }
                        )
                        raise FatalLLMError(f"{spec.name} 调用不可恢复失败: {error_text}") from exc
                    retryable = attempt_idx < max_attempts and (is_timeout or is_transient)
                    if retryable:
                        # 短暂故障重试前允许压缩 prompt / 降低 token，尽量用更小代价拿到一次可用输出。
                        logger.warning(
                            "runtime_agent_llm_retry",
                            session_id=orchestrator.session_id,
                            agent_name=spec.name,
                            phase=spec.phase,
                            loop_round=loop_round,
                            round_number=round_number,
                            attempt=attempt_idx,
                            max_attempts=max_attempts,
                            timeout_seconds=attempt_timeout,
                            latency_ms=latency_ms,
                            error=error_text,
                            retry_compacted=(attempt_prompt != prompt),
                        )
                        next_prompt, next_max_tokens, compacted = orchestrator._prepare_timeout_retry_input(
                            spec=spec,
                            prompt=attempt_prompt,
                            max_tokens=attempt_max_tokens,
                        )
                        await orchestrator._emit_event(
                            {
                                "type": "llm_call_retry",
                                "phase": spec.phase,
                                "agent_name": spec.name,
                                "model": model_name,
                                "session_id": orchestrator.session_id,
                                "attempt": attempt_idx + 1,
                                "max_attempts": max_attempts,
                                "reason": error_text,
                                "latency_ms": latency_ms,
                                "retry_compacted": compacted,
                            }
                        )
                        attempt_prompt = next_prompt
                        attempt_max_tokens = next_max_tokens
                        if compacted:
                            logger.info(
                                "runtime_agent_llm_retry_compacted",
                                session_id=orchestrator.session_id,
                                agent_name=spec.name,
                                phase=spec.phase,
                                loop_round=loop_round,
                                round_number=round_number,
                                next_prompt_length=len(attempt_prompt),
                                next_max_tokens=attempt_max_tokens,
                            )
                            await orchestrator._emit_event(
                                {
                                    "type": "llm_call_retry_compacted",
                                    "phase": spec.phase,
                                    "agent_name": spec.name,
                                    "model": model_name,
                                    "session_id": orchestrator.session_id,
                                    "next_prompt_length": len(attempt_prompt),
                                    "next_max_tokens": attempt_max_tokens,
                                }
                            )
                        raise RetryableAgentTimeoutError(error_text) from exc

                    failure_type = "timeout" if is_timeout else ("transient_error" if is_transient else "error")
                    (logger.warning if (is_timeout or is_transient) else logger.error)(
                        "runtime_agent_llm_timeout" if is_timeout else "runtime_agent_llm_failed",
                        session_id=orchestrator.session_id,
                        agent_name=spec.name,
                        phase=spec.phase,
                        loop_round=loop_round,
                        round_number=round_number,
                        attempt=attempt_idx,
                        max_attempts=max_attempts,
                        timeout_seconds=attempt_timeout,
                        latency_ms=latency_ms,
                        error=error_text,
                    )
                    await orchestrator._emit_event(
                        {
                            "type": "llm_http_error",
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "session_id": orchestrator.session_id,
                            "model": model_name,
                            "endpoint": endpoint,
                            "error": error_text,
                            "latency_ms": latency_ms,
                        }
                    )
                    await orchestrator._emit_event(
                        {
                            "type": "llm_call_timeout" if is_timeout else "llm_call_failed",
                            **event_common,
                            "error": error_text,
                            "latency_ms": latency_ms,
                            "timeout_seconds": attempt_timeout,
                            "attempt": attempt_idx,
                            "max_attempts": max_attempts,
                            "prompt_preview": attempt_prompt[:1200],
                            "failure_type": failure_type,
                        }
                    )
                    await orchestrator._emit_event(
                        {
                            "type": "llm_request_failed",
                            **event_common,
                            "error": error_text,
                            "failure_type": failure_type,
                            "latency_ms": latency_ms,
                            "timeout_seconds": attempt_timeout,
                            "attempt": attempt_idx,
                            "max_attempts": max_attempts,
                            "prompt_preview": attempt_prompt[:1200],
                        }
                    )
                    raise RuntimeError(f"{spec.name} 调用失败: {error_text}") from exc
    except RetryableAgentTimeoutError as exc:
        error_text = str(exc).strip() or "timeout"
        raise RuntimeError(f"{spec.name} 调用失败: {error_text}") from exc
