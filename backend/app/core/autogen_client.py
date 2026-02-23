"""
AutoGen-backed LLM client.

This client keeps the existing session/send_prompt interface used by services,
while the underlying call path is implemented with pyautogen agents.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

import autogen
import structlog

from app.config import settings
from app.core.circuit_breaker import CircuitBreaker
from app.core.event_schema import enrich_event, new_trace_id
from app.core.json_utils import extract_json_dict

logger = structlog.get_logger()


@dataclass
class AutoGenConfig:
    timeout: int = settings.llm_timeout


@dataclass
class SessionInfo:
    id: str
    title: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class _SessionState:
    id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    system_prompts: List[str] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)


class AutoGenClient:
    _LOG_TEXT_LIMIT = 4000
    _STREAM_CHUNK_SIZE = 120
    _STREAM_MAX_CHUNKS = 24

    def __init__(self, config: Optional[AutoGenConfig] = None):
        self.config = config or AutoGenConfig()
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_SECONDS,
        )
        self._llm_semaphore = asyncio.Semaphore(max(1, int(settings.LLM_MAX_CONCURRENCY or 1)))
        self._sessions: Dict[str, _SessionState] = {}
        logger.info(
            "autogen_client_initialized",
            backend="pyautogen",
            model=settings.llm_model,
            base_url=settings.LLM_BASE_URL,
        )

    async def close(self) -> None:
        return None

    async def health_check(self) -> Dict[str, Any]:
        return {
            "healthy": True,
            "backend": "pyautogen",
            "model": settings.llm_model,
            "base_url": settings.LLM_BASE_URL,
            "endpoint": self._chat_endpoint(),
        }

    async def list_agents(self) -> List[Dict[str, Any]]:
        return [{"id": "autogen_runtime", "name": "AutoGen Runtime"}]

    async def write_log(self, service: str, level: str, message: str) -> bool:
        logger.info("external_log", service=service, level=level, message=message)
        return True

    async def get_providers(self) -> Dict[str, Any]:
        return {
            "providers": [{"id": settings.llm_provider_id, "models": [settings.llm_model]}],
            "default": {"providerID": settings.llm_provider_id, "modelID": settings.llm_model},
        }

    async def create_session(
        self,
        title: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> SessionInfo:
        _ = parent_id
        now = datetime.utcnow().isoformat()
        session_id = f"ses_{uuid4().hex[:24]}"
        self._sessions[session_id] = _SessionState(
            id=session_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        logger.info("llm_session_created", session_id=session_id, title=title)
        return SessionInfo(id=session_id, title=title, created_at=now, updated_at=now)

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        state = self._sessions.get(session_id)
        if not state:
            raise ValueError(f"Session not found: {session_id}")
        return {
            "id": state.id,
            "title": state.title,
            "createdAt": state.created_at,
            "updatedAt": state.updated_at,
        }

    async def list_sessions(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": s.id,
                "title": s.title,
                "createdAt": s.created_at,
                "updatedAt": s.updated_at,
            }
            for s in self._sessions.values()
        ]

    async def delete_session(self, session_id: str) -> bool:
        self._sessions.pop(session_id, None)
        return True

    async def abort_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        state = self._sessions.get(session_id)
        if not state:
            return []
        return list(state.messages)

    @staticmethod
    def _normalize_model(model: Dict[str, Any]) -> Dict[str, Any]:
        model_id = model.get("modelID") or model.get("name") or settings.llm_model
        provider_id = model.get("providerID") or settings.llm_provider_id
        return {"providerID": provider_id, "modelID": model_id}

    @staticmethod
    def _extract_text_parts(parts: List[Dict[str, Any]]) -> str:
        texts: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") != "text":
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
        return "\n\n".join(texts).strip()

    @staticmethod
    def _schema_payload(format_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(format_payload, dict):
            return None
        if format_payload.get("type") != "json_schema":
            return None
        schema = format_payload.get("schema")
        if not isinstance(schema, dict):
            return None
        return schema

    @staticmethod
    def _schema_instruction(schema: Optional[Dict[str, Any]]) -> str:
        if not isinstance(schema, dict):
            return ""
        return (
            "\n\n请严格输出且仅输出一个 JSON 对象，必须符合以下 JSON Schema：\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )

    @staticmethod
    def _history_context(messages: List[Dict[str, Any]], max_items: int = 6) -> str:
        if not messages:
            return ""
        selected = messages[-max_items:]
        lines: List[str] = []
        for item in selected:
            role = str(item.get("role", "assistant"))
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"[{role}] {content[:900]}")
        if not lines:
            return ""
        return "以下是最近会话核心观点：\n" + "\n".join(lines)

    @staticmethod
    def _base_url_for_autogen() -> str:
        base = settings.LLM_BASE_URL.rstrip("/")
        if base.endswith("/v1") or base.endswith("/v3"):
            return base
        return f"{base}/v3"

    @classmethod
    def _chat_endpoint(cls) -> str:
        base = cls._base_url_for_autogen()
        return f"{base}/chat/completions"

    @classmethod
    def _truncate_text(cls, text: Any, limit: Optional[int] = None) -> str:
        if text is None:
            return ""
        value = str(text)
        max_len = limit or cls._LOG_TEXT_LIMIT
        if len(value) <= max_len:
            return value
        return f"{value[:max_len]}...<truncated:{len(value) - max_len}>"

    @classmethod
    def _sanitize_messages_for_log(cls, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        sanitized: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", "user"))
            content = str(msg.get("content", ""))
            sanitized.append(
                {
                    "role": role,
                    "content_preview": cls._truncate_text(content),
                    "content_length": len(content),
                }
            )
        return sanitized

    @staticmethod
    def _is_rate_limited_error(error_text: str) -> bool:
        normalized = str(error_text or "").lower()
        return (
            "429" in normalized
            or "toomanyrequests" in normalized
            or "serveroverloaded" in normalized
            or "rate limit" in normalized
        )

    async def _emit_trace_event(
        self,
        trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        event: Dict[str, Any],
    ) -> None:
        if not trace_callback:
            return
        try:
            payload = enrich_event(
                event,
                trace_id=str(event.get("trace_id") or new_trace_id("llm")),
                default_phase=str(event.get("phase") or ""),
            )
            maybe = trace_callback(payload)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception as exc:
            logger.warning("autogen_trace_event_emit_failed", error=str(exc))

    def _run_autogen_reply(
        self,
        prompt: str,
        system_prompt: str,
        model_name: str,
        agent_name: str,
        max_tokens: Optional[int] = None,
    ) -> str:
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY 未配置，无法调用模型")
        llm_config = {
            "config_list": [
                {
                    "model": model_name,
                    "api_key": settings.LLM_API_KEY,
                    "base_url": self._base_url_for_autogen(),
                    "price": [0, 0],
                }
            ],
            "temperature": 0.2,
            "timeout": max(10, min(settings.llm_timeout, 45)),
        }
        if isinstance(max_tokens, int) and max_tokens > 0:
            llm_config["max_tokens"] = max_tokens

        assistant = autogen.AssistantAgent(
            name=agent_name or "AutoGenAgent",
            system_message=system_prompt or "你是严谨的 SRE 分析助手。",
            llm_config=llm_config,
            human_input_mode="NEVER",
        )

        reply = assistant.generate_reply(
            messages=[{"role": "user", "content": prompt}],
        )
        if isinstance(reply, dict):
            content = reply.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            return json.dumps(reply, ensure_ascii=False)
        if isinstance(reply, str):
            return reply.strip()
        return json.dumps(reply, ensure_ascii=False)

    async def _repair_structured_output(
        self,
        content: str,
        schema: Dict[str, Any],
        model_name: str,
        session_id: str,
        trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        trace_context = trace_context or {}
        trace_id = str(trace_context.get("trace_id") or new_trace_id("llm"))
        repair_prompt = (
            "请将以下文本修复为严格符合 JSON Schema 的 JSON 对象，仅输出 JSON 对象，不要输出解释。\n\n"
            f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"待修复文本:\n{self._truncate_text(content, 3000)}"
        )
        await self._emit_trace_event(
            trace_callback,
            {
                "type": "llm_output_repair_started",
                "phase": trace_context.get("phase"),
                "stage": "json_repair",
                "session_id": session_id,
                "model": model_name,
                "trace_id": trace_id,
            },
        )

        try:
            async with self._llm_semaphore:
                fixed = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._run_autogen_reply,
                        repair_prompt,
                        "你是严格的 JSON 修复器。",
                        model_name,
                        "JsonRepairAgent",
                        480,
                    ),
                    timeout=float(max(12, min(settings.llm_total_timeout, 40))),
                )
            repaired = extract_json_dict(fixed) or {}
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_output_repair_completed",
                    "phase": trace_context.get("phase"),
                    "stage": "json_repair",
                    "session_id": session_id,
                    "model": model_name,
                    "trace_id": trace_id,
                    "structured": bool(repaired),
                },
            )
            return repaired
        except Exception as exc:
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_output_repair_failed",
                    "phase": trace_context.get("phase"),
                    "stage": "json_repair",
                    "session_id": session_id,
                    "model": model_name,
                    "trace_id": trace_id,
                    "error": str(exc),
                },
            )
            return {}

    async def send_prompt(
        self,
        session_id: str,
        parts: List[Dict[str, Any]],
        model: Optional[Dict[str, str]] = None,
        agent: Optional[str] = None,
        no_reply: bool = False,
        use_session_history: bool = True,
        max_tokens: Optional[int] = None,
        format: Optional[Dict[str, Any]] = None,
        trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._circuit_breaker.allow_request():
            raise RuntimeError("LLM circuit breaker is open")
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY 未配置，无法调用模型")

        state = self._sessions.get(session_id)
        if not state:
            raise ValueError(f"Session not found: {session_id}")

        normalized_model = self._normalize_model(model or {})
        model_name = normalized_model.get("modelID") or settings.llm_model
        prompt_text = self._extract_text_parts(parts)
        if not prompt_text:
            raise ValueError("Prompt text is empty")

        schema = self._schema_payload(format)
        trace_context = trace_context or {}
        trace_id = str(trace_context.get("trace_id") or new_trace_id("llm"))
        trace_context = {**trace_context, "trace_id": trace_id}
        prompt_with_schema = prompt_text + self._schema_instruction(schema)

        if no_reply:
            state.system_prompts.append(prompt_text)
            state.updated_at = datetime.utcnow().isoformat()
            state.messages.append(
                {"role": "system", "content": prompt_text, "timestamp": state.updated_at}
            )
            return {"content": "", "info": {"no_reply": True}}

        history_text = self._history_context(state.messages) if use_session_history else ""
        system_prompt = "\n\n".join(state.system_prompts).strip()
        effective_prompt = "\n\n".join(
            [item for item in [history_text, prompt_with_schema] if item]
        )

        started_at = perf_counter()
        request_payload_log = {
            "model": model_name,
            "max_tokens": max_tokens,
            "message_count": 2,
            "messages": self._sanitize_messages_for_log(
                [
                    {"role": "system", "content": system_prompt or "(empty)"},
                    {"role": "user", "content": effective_prompt},
                ]
            ),
            "base_url": self._base_url_for_autogen(),
        }
        endpoint = self._chat_endpoint()

        await self._emit_trace_event(
            trace_callback,
            {
                "type": "llm_call_started",
                "phase": trace_context.get("phase"),
                "stage": trace_context.get("stage"),
                "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                "model": model_name,
                "session_id": session_id,
                "prompt_preview": effective_prompt[:1200],
                "trace_id": trace_id,
            },
        )
        await self._emit_trace_event(
            trace_callback,
            {
                "type": "autogen_call_started",
                "phase": trace_context.get("phase"),
                "stage": trace_context.get("stage"),
                "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                "model": model_name,
                "session_id": session_id,
                "prompt_preview": effective_prompt[:1200],
                "trace_id": trace_id,
            },
        )
        await self._emit_trace_event(
            trace_callback,
            {
                "type": "llm_http_request",
                "phase": trace_context.get("phase"),
                "stage": trace_context.get("stage"),
                "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                "model": model_name,
                "session_id": session_id,
                "endpoint": endpoint,
                "request_payload": request_payload_log,
                "trace_id": trace_id,
            },
        )

        logger.info(
            "llm_request_started",
            backend="pyautogen",
            model=model_name,
            session_id=session_id,
            trace_id=trace_id,
            phase=trace_context.get("phase"),
            stage=trace_context.get("stage"),
            prompt_preview=self._truncate_text(effective_prompt, 1500),
        )

        try:
            async with self._llm_semaphore:
                content = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._run_autogen_reply,
                        effective_prompt,
                        system_prompt,
                        model_name,
                        trace_context.get("agent_name") or agent or "AutoGenAgent",
                        max_tokens,
                    ),
                    timeout=float(max(12, min(settings.llm_total_timeout, 45))),
                )

            structured = extract_json_dict(content) or {}
            if schema and not structured:
                structured = await self._repair_structured_output(
                    content=content,
                    schema=schema,
                    model_name=model_name,
                    session_id=session_id,
                    trace_callback=trace_callback,
                    trace_context=trace_context,
                )

            state.updated_at = datetime.utcnow().isoformat()
            state.messages.append(
                {"role": "user", "content": prompt_with_schema, "timestamp": state.updated_at}
            )
            state.messages.append(
                {"role": "assistant", "content": content, "timestamp": state.updated_at}
            )
            if len(state.messages) > 40:
                del state.messages[:-40]

            latency_ms = round((perf_counter() - started_at) * 1000, 2)
            self._circuit_breaker.record_success()
            await self._emit_stream_deltas(
                trace_callback=trace_callback,
                trace_context=trace_context,
                session_id=session_id,
                model_name=model_name,
                content=content,
            )

            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_http_response",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "endpoint": endpoint,
                    "status_code": 200,
                    "response_payload": {
                        "content_preview": content[:1500],
                        "content_length": len(content),
                        "structured": bool(structured),
                    },
                    "latency_ms": latency_ms,
                    "trace_id": trace_id,
                },
            )
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "autogen_call_completed",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "latency_ms": latency_ms,
                    "response_preview": content[:1500],
                    "structured": bool(structured),
                    "trace_id": trace_id,
                },
            )
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_call_completed",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "latency_ms": latency_ms,
                    "response_preview": content[:1500],
                    "trace_id": trace_id,
                },
            )

            logger.info(
                "llm_request_completed",
                backend="pyautogen",
                model=model_name,
                session_id=session_id,
                trace_id=trace_id,
                latency_ms=latency_ms,
                response_preview=self._truncate_text(content, 1200),
                structured=bool(structured),
            )

            return {
                "content": content,
                "structured": structured,
                "info": {
                    "provider": "autogen",
                    "model": model_name,
                    "session_id": state.id,
                    "endpoint": endpoint,
                    "structured": structured,
                    "structured_output": structured,
                    "trace_id": trace_id,
                },
            }
        except Exception as exc:
            self._circuit_breaker.record_failure()
            latency_ms = round((perf_counter() - started_at) * 1000, 2)
            error_text = str(exc).strip() or exc.__class__.__name__
            is_timeout = isinstance(exc, asyncio.TimeoutError) or "timeout" in error_text.lower()
            if settings.LLM_FAILFAST_ON_RATE_LIMIT and self._is_rate_limited_error(error_text):
                error_text = f"LLM_RATE_LIMITED: {error_text}"

            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_http_error",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "endpoint": endpoint,
                    "error": error_text,
                    "latency_ms": latency_ms,
                    "trace_id": trace_id,
                },
            )
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "autogen_call_timeout" if is_timeout else "autogen_call_failed",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "error": error_text,
                    "latency_ms": latency_ms,
                    "trace_id": trace_id,
                },
            )
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_call_timeout" if is_timeout else "llm_call_failed",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "error": error_text,
                    "latency_ms": latency_ms,
                    "trace_id": trace_id,
                },
            )
            log_method = logger.warning if is_timeout else logger.error
            log_method(
                "llm_request_timeout" if is_timeout else "llm_request_failed",
                backend="pyautogen",
                model=model_name,
                session_id=session_id,
                trace_id=trace_id,
                latency_ms=latency_ms,
                error=error_text,
            )
            raise

    async def _emit_stream_deltas(
        self,
        trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        trace_context: Dict[str, Any],
        session_id: str,
        model_name: str,
        content: str,
    ) -> None:
        text = (content or "").strip()
        if not text:
            return
        chunks = [text[i : i + self._STREAM_CHUNK_SIZE] for i in range(0, len(text), self._STREAM_CHUNK_SIZE)]
        truncated = False
        if len(chunks) > self._STREAM_MAX_CHUNKS:
            chunks = chunks[: self._STREAM_MAX_CHUNKS]
            truncated = True
        stream_id = f"{session_id}:{trace_context.get('agent_name') or 'autogen_agent'}"
        for index, chunk in enumerate(chunks, start=1):
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_stream_delta",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "stream_id": stream_id,
                    "chunk_index": index,
                    "chunk_total": len(chunks),
                    "delta": chunk,
                    "truncated": truncated,
                    "trace_id": trace_context.get("trace_id"),
                },
            )

    async def send_text_prompt(
        self,
        session_id: str,
        text: str,
        model: Optional[Dict[str, str]] = None,
        agent: Optional[str] = None,
        format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self.send_prompt(
            session_id=session_id,
            parts=[{"type": "text", "text": text}],
            model=model,
            agent=agent,
            format=format,
        )

    async def send_structured_prompt(
        self,
        session_id: str,
        text: str,
        schema: Dict[str, Any],
        model: Optional[Dict[str, str]] = None,
        agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.send_prompt(
            session_id=session_id,
            parts=[{"type": "text", "text": text}],
            model=model,
            agent=agent,
            format={"type": "json_schema", "schema": schema},
        )

    async def run_command(self, session_id: str, command: str) -> Dict[str, Any]:
        _ = (session_id, command)
        raise NotImplementedError("run_command is not supported")

    async def run_shell(self, session_id: str, command: str) -> Dict[str, Any]:
        _ = (session_id, command)
        raise NotImplementedError("run_shell is not supported")


_client_instance: Optional[AutoGenClient] = None


def get_autogen_client() -> AutoGenClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = AutoGenClient()
    return _client_instance


async def create_autogen_session(title: str) -> SessionInfo:
    client = get_autogen_client()
    return await client.create_session(title=title)


autogen_client = get_autogen_client()
