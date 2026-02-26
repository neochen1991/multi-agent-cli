"""Runtime execution helpers for LangGraph agent calls.

This module extracts the heavy LLM call orchestration path out of the main
runtime class so the orchestrator focuses on graph routing/state transitions.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from time import perf_counter
from typing import Any, Optional

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.llm_client import LLMClient
from app.runtime.langgraph.parsers import normalize_agent_output
from app.runtime.langgraph.state import AgentSpec, DebateTurn

logger = structlog.get_logger()


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


def run_agent_once(orchestrator: Any, spec: AgentSpec, prompt: str, max_tokens: int) -> str:
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
    return LLMClient._extract_reply_text(reply, agent_name=spec.name)


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

    last_exc: Optional[Exception] = None
    for attempt_idx, attempt_timeout in enumerate(timeout_plan, start=1):
        started_clock = perf_counter()
        try:
            queue_started = perf_counter()
            async with orchestrator._llm_semaphore:
                queue_wait_ms = round((perf_counter() - queue_started) * 1000, 2)
                logger.info(
                    "runtime_agent_llm_started",
                    session_id=orchestrator.session_id,
                    agent_name=spec.name,
                    phase=spec.phase,
                    loop_round=loop_round,
                    round_number=round_number,
                    attempt=attempt_idx,
                    max_attempts=len(timeout_plan),
                    timeout_seconds=attempt_timeout,
                    queue_wait_ms=queue_wait_ms,
                )
                raw_content = await asyncio.wait_for(
                    asyncio.to_thread(
                        run_agent_once,
                        orchestrator,
                        spec,
                        attempt_prompt,
                        attempt_max_tokens,
                    ),
                    timeout=attempt_timeout,
                )
            latency_ms = round((perf_counter() - started_clock) * 1000, 2)
            payload = normalize_agent_output(
                spec.name,
                raw_content,
                judge_fallback_summary=orchestrator.JUDGE_FALLBACK_SUMMARY,
            )
            if spec.name == "JudgeAgent":
                final_judgment = payload.get("final_judgment")
                root_cause = final_judgment.get("root_cause") if isinstance(final_judgment, dict) else {}
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
            )
            return turn
        except Exception as exc:
            last_exc = exc
            latency_ms = round((perf_counter() - started_clock) * 1000, 2)
            error_text = str(exc).strip() or exc.__class__.__name__
            is_timeout = isinstance(exc, asyncio.TimeoutError) or "timeout" in error_text.lower()
            if settings.LLM_FAILFAST_ON_RATE_LIMIT and orchestrator._is_rate_limited_error(error_text):
                error_text = f"LLM_RATE_LIMITED: {error_text}"
            retryable = attempt_idx < len(timeout_plan) and is_timeout
            if retryable:
                logger.warning(
                    "runtime_agent_llm_retry",
                    session_id=orchestrator.session_id,
                    agent_name=spec.name,
                    phase=spec.phase,
                    loop_round=loop_round,
                    round_number=round_number,
                    attempt=attempt_idx,
                    max_attempts=len(timeout_plan),
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
                        "max_attempts": len(timeout_plan),
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
                continue

            (logger.warning if is_timeout else logger.error)(
                "runtime_agent_llm_timeout" if is_timeout else "runtime_agent_llm_failed",
                session_id=orchestrator.session_id,
                agent_name=spec.name,
                phase=spec.phase,
                loop_round=loop_round,
                round_number=round_number,
                attempt=attempt_idx,
                max_attempts=len(timeout_plan),
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

    error_text = str(last_exc).strip() if last_exc else "unknown"
    raise RuntimeError(f"{spec.name} 调用失败: {error_text}")
