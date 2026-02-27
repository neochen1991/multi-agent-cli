"""Runtime execution helpers for LangGraph agent calls.

This module extracts the heavy LLM call orchestration path out of the main
runtime class so the orchestrator focuses on graph routing/state transitions.
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
from app.runtime.langgraph.state import AgentSpec, DebateTurn
from app.runtime.langgraph.schemas import get_schema_for_agent

logger = structlog.get_logger()


@dataclass
class AgentInvokeResult:
    content: str
    invoke_mode: str
    factory_error: str = ""


class RetryableAgentTimeoutError(RuntimeError):
    """Retry marker for timeout-like transient failures."""


async def emit_stream_deltas(
    orchestrator: Any,
    *,
    spec: AgentSpec,
    raw_content: str,
    loop_round: int,
    round_number: int,
) -> None:
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
    # Prefer AgentFactory (tool-enabled ReAct path) when configured and tools exist.
    factory_error = ""
    if settings.AGENT_USE_FACTORY and spec.name in {"LogAgent", "DomainAgent", "CodeAgent"} and tuple(spec.tools or ()):
        factory = orchestrator._get_agent_factory()
        if factory is not None:
            try:
                agent = factory.create_agent(
                    spec.name,
                    llm=llm,
                    tools=list(spec.tools),
                    system_prompt=spec.system_prompt or "",
                )
                response = agent.invoke({"messages": [HumanMessage(content=prompt)]})
                extracted = _extract_factory_text(response, agent_name=spec.name)
                if extracted.strip():
                    return AgentInvokeResult(
                        content=extracted,
                        invoke_mode="factory",
                    )
            except Exception as exc:
                # Fallback to direct invoke path below.
                factory_error = str(exc).strip() or exc.__class__.__name__
    reply = llm.invoke(
        [
            SystemMessage(content=spec.system_prompt or "你是严谨的 SRE 分析助手。"),
            HumanMessage(content=prompt),
        ]
    )
    return AgentInvokeResult(
        content=LLMClient._extract_reply_text(reply, agent_name=spec.name),
        invoke_mode="direct",
        factory_error=factory_error,
    )


def _extract_factory_text(response: Any, *, agent_name: str) -> str:
    # create_react_agent 常见返回: {"messages": [...]}
    if isinstance(response, dict):
        messages = response.get("messages")
        if isinstance(messages, list):
            for item in reversed(messages):
                if not isinstance(item, BaseMessage):
                    continue
                text = LLMClient._extract_reply_text(item, agent_name=agent_name)
                if text:
                    return text
    return LLMClient._extract_reply_text(response, agent_name=agent_name)


def run_agent_with_structured_output(
    orchestrator: Any,
    spec: AgentSpec,
    prompt: str,
    max_tokens: int,
) -> tuple[Dict[str, Any], str]:
    """
    Run agent with structured output validation using Pydantic.

    Uses LLM's with_structured_output for native structured output,
    falling back to manual parsing if needed.

    Args:
        orchestrator: Runtime orchestrator instance
        spec: Agent specification
        prompt: Input prompt
        max_tokens: Maximum tokens for response

    Returns:
        Tuple of (parsed_output_dict, invoke_mode)
    """
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

    # Get appropriate schema for agent
    schema = get_schema_for_agent(spec.name)

    try:
        # Try structured output mode
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

        # Fallback to regular invocation
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
    started_at = datetime.utcnow()
    model_name = settings.llm_model
    endpoint = orchestrator._chat_endpoint()
    agent_max_tokens = orchestrator._agent_max_tokens(spec.name)
    attempt_prompt = prompt
    attempt_max_tokens = agent_max_tokens

    await orchestrator._emit_event(
        {
            "type": "llm_call_started",
            "phase": spec.phase,
            "agent_name": spec.name,
            "model": model_name,
            "session_id": orchestrator.session_id,
            "loop_round": loop_round,
            "round_number": round_number,
            "prompt_preview": prompt[:1200],
        }
    )
    await orchestrator._emit_event(
        {
            "type": "llm_http_request",
            "phase": spec.phase,
            "agent_name": spec.name,
            "session_id": orchestrator.session_id,
            "model": model_name,
            "endpoint": endpoint,
            "request_payload": {
                "model": model_name,
                "max_tokens": agent_max_tokens,
                "message_count": 2,
                "prompt_length": len(prompt),
                "prompt_preview": prompt[:1200],
            },
        }
    )

    timeout_plan = orchestrator._agent_timeout_plan(spec.name)
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
    )

    max_attempts = max(1, len(timeout_plan))
    retrying = AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=2.0),
        retry=retry_if_exception_type(RetryableAgentTimeoutError),
        reraise=True,
    )

    try:
        async for attempt in retrying:
            attempt_idx = int(attempt.retry_state.attempt_number or 1)
            attempt_timeout = timeout_plan[min(attempt_idx - 1, len(timeout_plan) - 1)]
            started_clock = perf_counter()
            with attempt:
                try:
                    queue_started = perf_counter()
                    async with orchestrator._get_llm_semaphore():
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
                            queue_wait_ms=queue_wait_ms,
                        )
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
                    raw_content = str(getattr(invoke_result, "content", "") or "")
                    invoke_mode = str(getattr(invoke_result, "invoke_mode", "") or "direct")
                    factory_error = str(getattr(invoke_result, "factory_error", "") or "")
                    if invoke_mode == "direct" and factory_error:
                        await orchestrator._emit_event(
                            {
                                "type": "agent_factory_fallback",
                                "phase": spec.phase,
                                "agent_name": spec.name,
                                "session_id": orchestrator.session_id,
                                "model": model_name,
                                "reason": factory_error[:400],
                            }
                        )
                    await orchestrator._emit_event(
                        {
                            "type": "llm_invoke_path",
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "session_id": orchestrator.session_id,
                            "model": model_name,
                            "invoke_mode": invoke_mode,
                            "factory_enabled": bool(settings.AGENT_USE_FACTORY),
                            "tool_count": len(tuple(spec.tools or ())),
                        }
                    )
                    latency_ms = round((perf_counter() - started_clock) * 1000, 2)
                    payload = normalize_agent_output(
                        spec.name,
                        raw_content,
                        judge_fallback_summary=orchestrator.JUDGE_FALLBACK_SUMMARY,
                    )
                    if spec.name == "JudgeAgent":
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
                            },
                            "latency_ms": latency_ms,
                            "invoke_mode": invoke_mode,
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
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "model": model_name,
                            "session_id": orchestrator.session_id,
                            "response_preview": raw_content[:1200],
                            "latency_ms": latency_ms,
                            "invoke_mode": invoke_mode,
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
                    )
                    return turn
                except Exception as exc:
                    latency_ms = round((perf_counter() - started_clock) * 1000, 2)
                    error_text = str(exc).strip() or exc.__class__.__name__
                    is_timeout = isinstance(exc, asyncio.TimeoutError) or "timeout" in error_text.lower()
                    if settings.LLM_FAILFAST_ON_RATE_LIMIT and orchestrator._is_rate_limited_error(error_text):
                        error_text = f"LLM_RATE_LIMITED: {error_text}"
                    retryable = attempt_idx < max_attempts and is_timeout
                    if retryable:
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

                    (logger.warning if is_timeout else logger.error)(
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
                            "phase": spec.phase,
                            "agent_name": spec.name,
                            "model": model_name,
                            "session_id": orchestrator.session_id,
                            "error": error_text,
                            "latency_ms": latency_ms,
                            "prompt_preview": attempt_prompt[:1200],
                        }
                    )
                    raise RuntimeError(f"{spec.name} 调用失败: {error_text}") from exc
    except RetryableAgentTimeoutError as exc:
        error_text = str(exc).strip() or "timeout"
        raise RuntimeError(f"{spec.name} 调用失败: {error_text}") from exc
