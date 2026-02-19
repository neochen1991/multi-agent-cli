"""
AutoGen-based LLM client.

This module provides a session-compatible client API used by services/flows,
while the actual model interaction is implemented via AutoGen agents.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

import httpx
import structlog

from app.config import settings
from app.core.circuit_breaker import CircuitBreaker
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

    def __init__(self, config: Optional[AutoGenConfig] = None):
        self.config = config or AutoGenConfig()
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_SECONDS,
        )
        self._sessions: Dict[str, _SessionState] = {}
        logger.info(
            "llm_client_initialized",
            backend="autogen",
            model=settings.llm_model,
            base_url=settings.LLM_BASE_URL,
        )

    async def close(self):
        return None

    async def health_check(self) -> Dict[str, Any]:
        return {
            "healthy": True,
            "backend": "autogen",
            "model": settings.llm_model,
            "base_url": settings.LLM_BASE_URL,
        }

    async def list_agents(self) -> List[Dict[str, Any]]:
        return [{"id": "autogen", "name": "AutoGen Agent Runtime"}]

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
        logger.warning("llm_session_created", session_id=session_id, title=title)
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
    def _history_context(messages: List[Dict[str, Any]], max_items: int = 8) -> str:
        if not messages:
            return ""
        selected = messages[-max_items:]
        lines: List[str] = []
        for item in selected:
            role = str(item.get("role", "assistant"))
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"[{role}] {content[:1200]}")
        if not lines:
            return ""
        return "以下是最近会话上下文：\n" + "\n".join(lines)

    @staticmethod
    def _build_endpoint_candidates() -> List[str]:
        base = settings.LLM_BASE_URL.rstrip("/")
        candidates = [
            f"{base}/v3/chat/completions",
            f"{base}/chat/completions",
            f"{base}/v1/chat/completions",
        ]
        deduped: List[str] = []
        for item in candidates:
            if item not in deduped:
                deduped.append(item)
        return deduped

    @staticmethod
    def _extract_api_error(payload: Any) -> str:
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                msg = err.get("message")
                code = err.get("code")
                if msg and code:
                    return f"{code}: {msg}"
                if msg:
                    return str(msg)
            message = payload.get("message")
            if message:
                return str(message)
        return str(payload)[:1000]

    @staticmethod
    def _extract_response_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""

        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                content = first.get("text")
                if isinstance(content, str) and content.strip():
                    return content.strip()

        output = payload.get("output")
        if isinstance(output, dict):
            text = output.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()

        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        return ""

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

    @classmethod
    def _summarize_response_for_log(cls, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "payload_type": type(payload).__name__,
                "payload_preview": cls._truncate_text(payload),
            }
        return {
            "keys": list(payload.keys())[:20],
            "usage": payload.get("usage"),
            "choices_count": len(payload.get("choices", [])) if isinstance(payload.get("choices"), list) else 0,
            "content_preview": cls._truncate_text(cls._extract_response_text(payload)),
        }

    async def _call_remote_llm(
        self,
        prompt: str,
        system_prompt: str,
        model_name: str,
        agent_name: str,
        max_tokens: Optional[int] = None,
        request_meta: Optional[Dict[str, Any]] = None,
        trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request_meta = request_meta or {}
        trace_context = trace_context or {}
        headers = {
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        if isinstance(max_tokens, int) and max_tokens > 0:
            payload["max_tokens"] = max_tokens
        request_payload_log = {
            "model": payload["model"],
            "temperature": payload["temperature"],
            "stream": payload["stream"],
            "max_tokens": payload.get("max_tokens"),
            "message_count": len(messages),
            "messages": self._sanitize_messages_for_log(messages),
        }
        last_error = "unknown_error"
        request_timeout = httpx.Timeout(
            timeout=max(20.0, float(min(self.config.timeout, 120))),
            connect=10.0,
        )
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            for endpoint in self._build_endpoint_candidates():
                await self._emit_trace_event(
                    trace_callback,
                    {
                        "type": "llm_http_request",
                        "timestamp": datetime.utcnow().isoformat(),
                        "phase": trace_context.get("phase"),
                        "stage": trace_context.get("stage"),
                        "agent_name": agent_name,
                        "model": model_name,
                        "session_id": request_meta.get("session_id"),
                        "endpoint": endpoint,
                        "request_payload": request_payload_log,
                    },
                )
                logger.warning(
                    "llm_http_request_payload",
                    endpoint=endpoint,
                    agent=agent_name,
                    session_id=request_meta.get("session_id"),
                    phase=request_meta.get("phase"),
                    stage=request_meta.get("stage"),
                    payload=request_payload_log,
                )
                try:
                    response = await client.post(endpoint, headers=headers, json=payload)
                except Exception as exc:
                    last_error = f"{endpoint}: {str(exc)}"
                    logger.error(
                        "llm_http_request_exception",
                        endpoint=endpoint,
                        agent=agent_name,
                        error=str(exc),
                    )
                    continue

                if response.status_code == 404:
                    last_error = f"{endpoint}: 404_not_found"
                    continue

                if response.status_code >= 400:
                    try:
                        error_payload = response.json()
                    except Exception:
                        error_payload = {"message": response.text[:1000]}
                    await self._emit_trace_event(
                        trace_callback,
                        {
                            "type": "llm_http_error",
                            "timestamp": datetime.utcnow().isoformat(),
                            "phase": trace_context.get("phase"),
                            "stage": trace_context.get("stage"),
                            "agent_name": agent_name,
                            "model": model_name,
                            "session_id": request_meta.get("session_id"),
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "response_payload": self._truncate_text(error_payload),
                        },
                    )
                    logger.error(
                        "llm_http_response_error",
                        endpoint=endpoint,
                        status_code=response.status_code,
                        agent=agent_name,
                        session_id=request_meta.get("session_id"),
                        phase=request_meta.get("phase"),
                        stage=request_meta.get("stage"),
                        response=self._truncate_text(error_payload),
                    )
                    error_text = self._extract_api_error(error_payload)
                    raise RuntimeError(
                        f"LLM API error [{response.status_code}] at {endpoint}: {error_text}"
                    )

                try:
                    response_payload = response.json()
                except Exception as exc:
                    raise RuntimeError(f"LLM API non-JSON response at {endpoint}: {str(exc)}") from exc

                content = self._extract_response_text(response_payload)
                if not content:
                    raise RuntimeError(f"LLM API empty content at {endpoint}")
                response_log = self._summarize_response_for_log(response_payload)
                await self._emit_trace_event(
                    trace_callback,
                    {
                        "type": "llm_http_response",
                        "timestamp": datetime.utcnow().isoformat(),
                        "phase": trace_context.get("phase"),
                        "stage": trace_context.get("stage"),
                        "agent_name": agent_name,
                        "model": model_name,
                        "session_id": request_meta.get("session_id"),
                        "endpoint": endpoint,
                        "status_code": response.status_code,
                        "response_payload": response_log,
                    },
                )
                logger.warning(
                    "llm_http_response_payload",
                    endpoint=endpoint,
                    status_code=response.status_code,
                    agent=agent_name,
                    session_id=request_meta.get("session_id"),
                    phase=request_meta.get("phase"),
                    stage=request_meta.get("stage"),
                    response=response_log,
                )

                return {
                    "content": content,
                    "endpoint": endpoint,
                    "usage": response_payload.get("usage"),
                }

        raise RuntimeError(f"All LLM endpoints failed: {last_error}")

    async def _emit_trace_event(
        self,
        trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        event: Dict[str, Any],
    ) -> None:
        if not trace_callback:
            return
        try:
            maybe = trace_callback(event)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception as exc:
            logger.warning("autogen_trace_event_emit_failed", error=str(exc))

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
        effective_prompt_parts = [history_text, prompt_with_schema]
        effective_prompt = "\n\n".join([p for p in effective_prompt_parts if p])

        started_at = time.perf_counter()
        await self._emit_trace_event(
            trace_callback,
            {
                "type": "autogen_call_started",
                "timestamp": datetime.utcnow().isoformat(),
                "phase": trace_context.get("phase"),
                "stage": trace_context.get("stage"),
                "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                "model": model_name,
                "session_id": session_id,
                "prompt_preview": effective_prompt[:1200],
            },
        )
        logger.warning(
            "llm_request_started",
            backend="autogen",
            session_id=session_id,
            model=model_name,
            agent=agent,
            phase=trace_context.get("phase"),
            stage=trace_context.get("stage"),
            prompt_preview=self._truncate_text(effective_prompt, 1500),
        )

        try:
            call_result = await self._call_remote_llm(
                prompt=effective_prompt,
                system_prompt=system_prompt,
                model_name=model_name,
                agent_name=trace_context.get("agent_name") or agent or "AutoGenAgent",
                max_tokens=max_tokens,
                request_meta={
                    "session_id": session_id,
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                },
                trace_callback=trace_callback,
                trace_context=trace_context,
            )
            content = call_result["content"]
            endpoint = call_result["endpoint"]
            usage = call_result.get("usage")
            structured = extract_json_dict(content) or {}
            state.updated_at = datetime.utcnow().isoformat()
            state.messages.append(
                {"role": "user", "content": prompt_with_schema, "timestamp": state.updated_at}
            )
            state.messages.append(
                {"role": "assistant", "content": content, "timestamp": state.updated_at}
            )
            if len(state.messages) > 40:
                del state.messages[:-40]
            self._circuit_breaker.record_success()
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.warning(
                "llm_request_completed",
                backend="autogen",
                session_id=session_id,
                model=model_name,
                agent=agent,
                latency_ms=latency_ms,
                response_len=len(content),
                endpoint=endpoint,
                response_preview=self._truncate_text(content, 1500),
                usage=usage,
            )
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "autogen_call_completed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "latency_ms": latency_ms,
                    "endpoint": endpoint,
                    "response_preview": content[:1500],
                    "structured": bool(structured),
                    "usage": usage,
                },
            )
            return {
                "content": content,
                "structured": structured,
                "info": {
                    "provider": "autogen",
                    "model": model_name,
                    "session_id": state.id,
                    "endpoint": endpoint,
                    "usage": usage,
                    "structured": structured,
                    "structured_output": structured,
                },
            }
        except Exception as exc:
            self._circuit_breaker.record_failure()
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.error(
                "llm_request_failed",
                backend="autogen",
                session_id=session_id,
                model=model_name,
                agent=agent,
                phase=trace_context.get("phase"),
                stage=trace_context.get("stage"),
                prompt_preview=self._truncate_text(effective_prompt, 1500),
                error=str(exc),
                latency_ms=latency_ms,
            )
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "autogen_call_failed",
                    "timestamp": datetime.utcnow().isoformat(),
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "autogen_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "latency_ms": latency_ms,
                    "error": str(exc),
                },
            )
            raise

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
