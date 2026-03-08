"""
LLM 客户端模块

本模块提供与 LLM 服务交互的统一接口，基于 LangChain/LangGraph 实现。

核心功能：
1. 会话管理（创建、查询、删除）
2. 消息发送（支持文本和结构化输出）
3. 熔断保护（防止级联故障）
4. 并发控制（信号量限制）
5. 流式输出（支持增量推送）

工作流程：
1. 创建会话 -> 获取 session_id
2. 构建 prompt -> 调用 send_prompt
3. LLM 调用 -> 熔断检查 -> 并发控制 -> HTTP 请求
4. 解析响应 -> 提取文本/JSON
5. 返回结果 -> 记录日志

关键特性：
- 熔断器保护：失败次数过多时自动熔断
- 并发控制：使用信号量限制并发请求数
- 超时控制：按阶段配置不同超时时间
- 结构化输出：支持 JSON Schema 格式约束
- 流式推送：将响应分块推送给前端

LangGraph/LangChain-backed LLM client (compat layer).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.circuit_breaker import CircuitBreaker
from app.core.event_schema import enrich_event, new_trace_id
from app.core.json_utils import extract_json_dict

logger = structlog.get_logger()


def _build_llm_log_refs(
    *,
    session_id: str,
    trace_id: str,
    agent_name: str,
    phase: str,
    stage: str,
    prompt: str = "",
    system_prompt: str = "",
    response: str = "",
) -> Dict[str, str]:
    """按调试开关保存完整 LLM 文本，并返回 ref_id。"""
    from app.runtime.langgraph.output_truncation import save_output_reference

    refs: Dict[str, str] = {}
    metadata = {
        "trace_id": trace_id,
        "agent_name": agent_name,
        "phase": phase,
        "stage": stage,
    }
    if settings.LLM_LOG_FULL_PROMPT:
        if system_prompt:
            refs["system_prompt_ref"] = save_output_reference(
                content=system_prompt,
                session_id=session_id,
                category="llm_client_system_prompt",
                metadata=metadata,
            )
        if prompt:
            refs["prompt_ref"] = save_output_reference(
                content=prompt,
                session_id=session_id,
                category="llm_client_prompt",
                metadata=metadata,
            )
    if settings.LLM_LOG_FULL_RESPONSE and response:
        refs["response_ref"] = save_output_reference(
            content=response,
            session_id=session_id,
            category="llm_client_response",
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
class LLMClientConfig:
    """
    LLM 客户端配置

    属性：
    - timeout: 请求超时时间（秒）
    """
    timeout: int = settings.llm_timeout


@dataclass
class SessionInfo:
    """
    会话信息

    表示一个 LLM 会话的元数据。

    属性：
    - id: 会话 ID
    - title: 会话标题
    - created_at: 创建时间
    - updated_at: 更新时间
    """
    id: str
    title: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class _SessionState:
    """
    会话状态（内部使用）

    存储会话的完整状态，包括：
    - 元数据（ID、标题、时间）
    - 系统提示词列表
    - 消息历史

    属性：
    - id: 会话 ID
    - title: 会话标题
    - created_at: 创建时间
    - updated_at: 更新时间
    - system_prompts: 系统提示词列表
    - messages: 消息历史
    """
    id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    system_prompts: List[str] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)


class LLMClient:
    """
    LLM 客户端

    提供与 LLM 服务交互的统一接口。

    核心功能：
    - 会话管理：创建、查询、删除会话
    - 消息发送：支持文本和结构化输出
    - 熔断保护：失败次数过多时自动熔断
    - 并发控制：限制并发请求数
    - 流式输出：支持增量推送

    属性：
    - config: 客户端配置
    - _circuit_breaker: 熔断器实例
    - _llm_semaphore: 并发控制信号量
    - _sessions: 会话状态存储

    常量：
    - _LOG_TEXT_LIMIT: 日志文本截断长度
    - _STREAM_CHUNK_SIZE: 流式输出块大小
    - _STREAM_MAX_CHUNKS: 最大流式块数
    """
    _LOG_TEXT_LIMIT = 4000
    _STREAM_CHUNK_SIZE = 120
    _STREAM_MAX_CHUNKS = 24

    def __init__(self, config: Optional[LLMClientConfig] = None):
        """
        初始化 LLM 客户端

        设置熔断器、并发控制和会话存储。

        Args:
            config: 客户端配置，未提供则使用默认配置
        """
        self.config = config or LLMClientConfig()

        # 初始化熔断器
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_SECONDS,
        )

        # 初始化并发控制信号量
        self._llm_semaphore = asyncio.Semaphore(max(1, int(settings.LLM_MAX_CONCURRENCY or 1)))

        # 初始化会话存储
        self._sessions: Dict[str, _SessionState] = {}

        logger.info(
            "llm_client_initialized",
            backend="langgraph",
            model=settings.llm_model,
            base_url=settings.LLM_BASE_URL,
        )

    async def close(self) -> None:
        """
        关闭客户端

        清理资源（当前为空实现）。
        """
        return None

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        返回客户端状态信息。

        Returns:
            Dict[str, Any]: 健康状态信息
        """
        return {
            "healthy": True,
            "backend": "langgraph",
            "model": settings.llm_model,
            "base_url": settings.LLM_BASE_URL,
            "endpoint": self._chat_endpoint(),
        }

    async def list_agents(self) -> List[Dict[str, Any]]:
        """
        列出可用 Agent

        Returns:
            List[Dict[str, Any]]: Agent 列表
        """
        return [{"id": "langgraph_runtime", "name": "LangGraph Runtime"}]

    async def write_log(self, service: str, level: str, message: str) -> bool:
        """
        写入外部日志

        Args:
            service: 服务名称
            level: 日志级别
            message: 日志消息

        Returns:
            bool: 是否成功
        """
        logger.info("external_log", service=service, level=level, message=message)
        return True

    async def get_providers(self) -> Dict[str, Any]:
        """
        获取 LLM 提供者信息

        Returns:
            Dict[str, Any]: 提供者信息
        """
        return {
            "providers": [{"id": settings.llm_provider_id, "models": [settings.llm_model]}],
            "default": {"providerID": settings.llm_provider_id, "modelID": settings.llm_model},
        }

    async def create_session(
        self,
        title: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> SessionInfo:
        """
        创建会话

        创建一个新的 LLM 会话。

        Args:
            title: 会话标题
            parent_id: 父会话 ID（未使用）

        Returns:
            SessionInfo: 会话信息
        """
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
        """
        获取会话信息

        Args:
            session_id: 会话 ID

        Returns:
            Dict[str, Any]: 会话信息

        Raises:
            ValueError: 会话不存在
        """
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
        """
        列出所有会话

        Returns:
            List[Dict[str, Any]]: 会话列表
        """
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
        """
        删除会话

        Args:
            session_id: 会话 ID

        Returns:
            bool: 是否成功
        """
        self._sessions.pop(session_id, None)
        return True

    async def abort_session(self, session_id: str) -> bool:
        """
        中止会话

        Args:
            session_id: 会话 ID

        Returns:
            bool: 会话是否存在
        """
        return session_id in self._sessions

    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取会话消息历史

        Args:
            session_id: 会话 ID

        Returns:
            List[Dict[str, Any]]: 消息列表
        """
        state = self._sessions.get(session_id)
        if not state:
            return []
        return list(state.messages)

    @staticmethod
    def _normalize_model(model: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化模型配置

        确保模型配置包含必要的字段。

        Args:
            model: 模型配置

        Returns:
            Dict[str, Any]: 标准化后的配置
        """
        model_id = model.get("modelID") or model.get("name") or settings.llm_model
        provider_id = model.get("providerID") or settings.llm_provider_id
        return {"providerID": provider_id, "modelID": model_id}

    @staticmethod
    def _extract_text_parts(parts: List[Dict[str, Any]]) -> str:
        """
        从消息部件中提取文本

        Args:
            parts: 消息部件列表

        Returns:
            str: 提取的文本
        """
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

    @classmethod
    def _extract_text_from_any(cls, value: Any, *, depth: int = 0) -> str:
        """
        从任意值中递归提取文本

        支持字符串、列表、字典等类型。

        Args:
            value: 任意值
            depth: 递归深度

        Returns:
            str: 提取的文本
        """
        if depth > 6 or value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                text = cls._extract_text_from_any(item, depth=depth + 1)
                if text:
                    parts.append(text)
            return "\n".join(part for part in parts if part).strip()
        if isinstance(value, dict):
            # 优先提取常见文本字段
            for key in (
                "content",
                "text",
                "output_text",
                "answer",
                "final_answer",
                "reasoning_content",
                "value",
                "message",
                "messages",
                "choices",
            ):
                if key in value:
                    text = cls._extract_text_from_any(value.get(key), depth=depth + 1)
                    if text:
                        return text
            return ""
        return str(value).strip()

    @classmethod
    def _extract_reply_text(cls, reply: Any, *, agent_name: str = "") -> str:
        """
        从 LLM 响应中提取文本

        支持多种响应格式，包括：
        - LangChain 消息对象
        - 字典格式
        - 回退解析

        Args:
            reply: LLM 响应对象
            agent_name: Agent 名称（用于日志）

        Returns:
            str: 提取的文本
        """
        # 尝试从 content 属性提取
        content = getattr(reply, "content", "")
        text = cls._extract_text_from_any(content)
        if text:
            return text

        # 尝试从 text 属性提取
        text_attr = getattr(reply, "text", None)
        if isinstance(text_attr, str):
            text = cls._extract_text_from_any(text_attr)
            if text:
                return text
        elif callable(text_attr):
            # message.text() 已弃用，可能有兼容性问题
            pass

        # 尝试从 additional_kwargs 和 response_metadata 提取
        fallback_sources = (
            ("additional_kwargs", ("content", "text", "output_text", "answer", "final_answer", "reasoning_content", "message", "choices")),
            ("response_metadata", ("content", "text", "output_text", "answer", "final_answer", "reasoning_content", "message", "choices")),
        )
        for source_name, candidate_keys in fallback_sources:
            source = getattr(reply, source_name, None)
            text = ""
            if isinstance(source, dict):
                for key in candidate_keys:
                    if key not in source:
                        continue
                    text = cls._extract_text_from_any(source.get(key))
                    if text:
                        break
            elif source is not None and source_name == "additional_kwargs":
                text = cls._extract_text_from_any(source)
            if text:
                logger.warning(
                    "llm_reply_text_fallback_used",
                    agent=agent_name,
                    source=source_name,
                    preview=cls._truncate_text(text, 500),
                )
                return text

        # 尝试序列化后提取
        for method_name in ("model_dump", "dict"):
            method = getattr(reply, method_name, None)
            if callable(method):
                try:
                    dumped = method()
                    text = ""
                    if isinstance(dumped, dict):
                        for key in ("content", "text", "output_text", "answer", "final_answer", "reasoning_content", "message", "choices", "additional_kwargs"):
                            if key not in dumped:
                                continue
                            text = cls._extract_text_from_any(dumped.get(key))
                            if text:
                                break
                    if text:
                        logger.warning(
                            "llm_reply_text_fallback_used",
                            agent=agent_name,
                            source=method_name,
                            preview=cls._truncate_text(text, 500),
                        )
                        return text
                except Exception:
                    continue

        # 记录解析失败
        logger.warning(
            "llm_reply_empty_after_parse",
            agent=agent_name,
            reply_type=type(reply).__name__,
            additional_kwargs_keys=sorted(list(getattr(reply, "additional_kwargs", {}).keys()))
            if isinstance(getattr(reply, "additional_kwargs", None), dict)
            else [],
            response_metadata_keys=sorted(list(getattr(reply, "response_metadata", {}).keys()))
            if isinstance(getattr(reply, "response_metadata", None), dict)
            else [],
        )
        return ""

    @staticmethod
    def _schema_payload(format_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        从格式配置中提取 JSON Schema

        Args:
            format_payload: 格式配置

        Returns:
            Optional[Dict[str, Any]]: JSON Schema，无效则返回 None
        """
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
        """
        生成 JSON Schema 约束指令

        Args:
            schema: JSON Schema

        Returns:
            str: 约束指令文本
        """
        if not isinstance(schema, dict):
            return ""
        return (
            "\n\n请严格输出且仅输出一个 JSON 对象，必须符合以下 JSON Schema：\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )

    @staticmethod
    def _history_context(messages: List[Dict[str, Any]], max_items: int = 6) -> str:
        """
        构建历史上下文

        从消息历史中提取最近的消息作为上下文。

        Args:
            messages: 消息历史
            max_items: 最大消息数

        Returns:
            str: 历史上下文文本
        """
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
    def _base_url_for_llm() -> str:
        """
        获取 LLM API 基础 URL

        确保 URL 以 /v1 或 /v3 结尾。

        Returns:
            str: 基础 URL
        """
        base = settings.LLM_BASE_URL.rstrip("/")
        if base.endswith("/v1") or base.endswith("/v3"):
            return base
        return f"{base}/v3"

    @classmethod
    def _chat_endpoint(cls) -> str:
        """
        获取聊天完成端点 URL

        Returns:
            str: 端点 URL
        """
        base = cls._base_url_for_llm()
        return f"{base}/chat/completions"

    @classmethod
    def _truncate_text(cls, text: Any, limit: Optional[int] = None) -> str:
        """
        截断文本

        用于日志输出时控制文本长度。

        Args:
            text: 文本内容
            limit: 长度限制

        Returns:
            str: 截断后的文本
        """
        if text is None:
            return ""
        value = str(text)
        max_len = limit or cls._LOG_TEXT_LIMIT
        if len(value) <= max_len:
            return value
        return f"{value[:max_len]}...<truncated:{len(value) - max_len}>"

    @classmethod
    def _sanitize_messages_for_log(cls, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        清理消息用于日志

        截断消息内容，避免日志过大。

        Args:
            messages: 消息列表

        Returns:
            List[Dict[str, Any]]: 清理后的消息列表
        """
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
        """
        判断是否为限流错误

        Args:
            error_text: 错误文本

        Returns:
            bool: 是否为限流错误
        """
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
        """
        发射追踪事件

        用于向调用方报告 LLM 调用过程。

        Args:
            trace_callback: 事件回调函数
            event: 事件数据
        """
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
            logger.warning("llm_trace_event_emit_failed", error=str(exc))

    @staticmethod
    def _phase_http_timeout(phase: Optional[str]) -> int:
        """
        获取阶段的 HTTP 超时时间

        不同阶段可能有不同的超时配置。

        Args:
            phase: 执行阶段

        Returns:
            int: 超时时间（秒）
        """
        phase_name = str(phase or "").strip().lower()
        if phase_name == "report_generation":
            return max(20, min(int(settings.llm_report_timeout_retry), 120))
        if phase_name == "asset_analysis":
            return max(20, min(int(settings.llm_asset_timeout), 90))
        return max(15, min(int(settings.llm_request_timeout), 90))

    @staticmethod
    def _phase_call_timeout(phase: Optional[str]) -> float:
        """
        获取阶段的调用超时时间

        Args:
            phase: 执行阶段

        Returns:
            float: 超时时间（秒）
        """
        phase_name = str(phase or "").strip().lower()
        if phase_name == "report_generation":
            return float(max(12, int(settings.llm_report_timeout_retry)))
        if phase_name == "asset_analysis":
            return float(max(12, int(settings.llm_asset_timeout)))
        return float(max(12, min(int(settings.llm_total_timeout), 60)))

    def _run_llm_reply(
        self,
        prompt: str,
        system_prompt: str,
        model_name: str,
        agent_name: str,
        max_tokens: Optional[int] = None,
        phase: Optional[str] = None,
    ) -> str:
        """
        同步执行 LLM 调用

        使用 LangChain ChatOpenAI 调用 LLM。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            model_name: 模型名称
            agent_name: Agent 名称
            max_tokens: 最大输出 token 数
            phase: 执行阶段

        Returns:
            str: LLM 响应文本

        Raises:
            RuntimeError: API Key 未配置
        """
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY 未配置，无法调用模型")

        llm = ChatOpenAI(
            model=model_name,
            api_key=settings.LLM_API_KEY,
            base_url=self._base_url_for_llm(),
            temperature=0.2,
            timeout=self._phase_http_timeout(phase),
            max_retries=max(0, int(settings.LLM_MAX_RETRIES)),
            max_tokens=(max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else None),
            model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
        )

        messages = [
            SystemMessage(content=system_prompt or "你是严谨的 SRE 分析助手。"),
            HumanMessage(content=prompt),
        ]

        reply = llm.invoke(messages)
        return self._extract_reply_text(reply, agent_name=agent_name)

    async def _repair_structured_output(
        self,
        content: str,
        schema: Dict[str, Any],
        model_name: str,
        session_id: str,
        trace_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        修复结构化输出

        当 LLM 输出不符合 JSON Schema 时，尝试修复。

        Args:
            content: 原始输出文本
            schema: JSON Schema
            model_name: 模型名称
            session_id: 会话 ID
            trace_callback: 追踪回调
            trace_context: 追踪上下文

        Returns:
            Dict[str, Any]: 修复后的结构化输出
        """
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
                        self._run_llm_reply,
                        repair_prompt,
                        "你是严格的 JSON 修复器。",
                        model_name,
                        "JsonRepairAgent",
                        480,
                        trace_context.get("phase"),
                    ),
                    timeout=min(self._phase_call_timeout(trace_context.get("phase")), 60.0),
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
        """
        发送提示词

        这是 LLM 客户端的核心方法，执行完整的 LLM 调用流程。

        流程：
        1. 熔断检查
        2. 会话验证
        3. 构建提示词（含历史上下文和 JSON Schema）
        4. 调用 LLM
        5. 解析响应（文本/JSON）
        6. 更新会话状态
        7. 流式推送

        Args:
            session_id: 会话 ID
            parts: 消息部件列表
            model: 模型配置
            agent: Agent 名称
            no_reply: 是否仅设置系统提示词
            use_session_history: 是否使用会话历史
            max_tokens: 最大输出 token 数
            format: 输出格式配置（JSON Schema）
            trace_callback: 追踪回调
            trace_context: 追踪上下文

        Returns:
            Dict[str, Any]: 响应结果，包含 content、structured、info

        Raises:
            RuntimeError: 熔断器打开或 API Key 未配置
            ValueError: 会话不存在或提示词为空
        """
        # 熔断检查
        if not self._circuit_breaker.allow_request():
            raise RuntimeError("LLM circuit breaker is open")
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY 未配置，无法调用模型")

        # 会话验证
        state = self._sessions.get(session_id)
        if not state:
            raise ValueError(f"Session not found: {session_id}")

        # 标准化模型配置
        normalized_model = self._normalize_model(model or {})
        model_name = normalized_model.get("modelID") or settings.llm_model

        # 提取提示词文本
        prompt_text = self._extract_text_parts(parts)
        if not prompt_text:
            raise ValueError("Prompt text is empty")

        # 提取 JSON Schema
        schema = self._schema_payload(format)

        # 构建追踪上下文
        trace_context = trace_context or {}
        trace_id = str(trace_context.get("trace_id") or new_trace_id("llm"))
        trace_context = {**trace_context, "trace_id": trace_id}

        # 附加 Schema 约束指令
        prompt_with_schema = prompt_text + self._schema_instruction(schema)

        # 仅设置系统提示词模式
        if no_reply:
            state.system_prompts.append(prompt_text)
            state.updated_at = datetime.utcnow().isoformat()
            state.messages.append(
                {"role": "system", "content": prompt_text, "timestamp": state.updated_at}
            )
            return {"content": "", "info": {"no_reply": True}}

        # 构建历史上下文
        history_text = self._history_context(state.messages) if use_session_history else ""
        system_prompt = "\n\n".join(state.system_prompts).strip()
        effective_prompt = "\n\n".join(
            [item for item in [history_text, prompt_with_schema] if item]
        )

        # 记录开始时间
        started_at = perf_counter()

        # 构建请求日志
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
            "base_url": self._base_url_for_llm(),
        }
        endpoint = self._chat_endpoint()
        prompt_refs = _build_llm_log_refs(
            session_id=session_id,
            trace_id=trace_id,
            agent_name=str(trace_context.get("agent_name") or agent or "llm_agent"),
            phase=str(trace_context.get("phase") or ""),
            stage=str(trace_context.get("stage") or ""),
            prompt=effective_prompt,
            system_prompt=system_prompt,
        )

        # 发射追踪事件
        await self._emit_trace_event(
            trace_callback,
            {
                "type": "llm_call_started",
                "phase": trace_context.get("phase"),
                "stage": trace_context.get("stage"),
                "agent_name": trace_context.get("agent_name") or agent or "llm_agent",
                "model": model_name,
                "session_id": session_id,
                "prompt_preview": effective_prompt[:1200],
                "trace_id": trace_id,
                **prompt_refs,
            },
        )
        await self._emit_trace_event(
            trace_callback,
            {
                "type": "llm_http_request",
                "phase": trace_context.get("phase"),
                "stage": trace_context.get("stage"),
                "agent_name": trace_context.get("agent_name") or agent or "llm_agent",
                "model": model_name,
                "session_id": session_id,
                "endpoint": endpoint,
                "request_payload": {**request_payload_log, **prompt_refs},
                "trace_id": trace_id,
                **prompt_refs,
            },
        )

        logger.info(
            "llm_request_started",
            backend="langgraph",
            model=model_name,
            session_id=session_id,
            trace_id=trace_id,
            phase=trace_context.get("phase"),
            stage=trace_context.get("stage"),
            prompt_preview=self._truncate_text(effective_prompt, 1500),
            prompt_ref=prompt_refs.get("prompt_ref"),
            system_prompt_ref=prompt_refs.get("system_prompt_ref"),
            full_prompt_logging=bool(settings.LLM_LOG_FULL_PROMPT),
        )
        if settings.LLM_LOG_FULL_PROMPT:
            logger.info(
                "llm_request_prompt_full",
                backend="langgraph",
                model=model_name,
                session_id=session_id,
                trace_id=trace_id,
                phase=trace_context.get("phase"),
                stage=trace_context.get("stage"),
                prompt_ref=prompt_refs.get("prompt_ref"),
                system_prompt_ref=prompt_refs.get("system_prompt_ref"),
                **_build_full_log_fields(
                    prompt=effective_prompt,
                    system_prompt=system_prompt,
                ),
            )

        try:
            # 执行 LLM 调用
            async with self._llm_semaphore:
                content = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._run_llm_reply,
                        effective_prompt,
                        system_prompt,
                        model_name,
                        trace_context.get("agent_name") or agent or "LLMAgent",
                        max_tokens,
                        trace_context.get("phase"),
                    ),
                    timeout=self._phase_call_timeout(trace_context.get("phase")),
                )

            # 提取结构化输出
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

            # 更新会话状态
            state.updated_at = datetime.utcnow().isoformat()
            state.messages.append(
                {"role": "user", "content": prompt_with_schema, "timestamp": state.updated_at}
            )
            state.messages.append(
                {"role": "assistant", "content": content, "timestamp": state.updated_at}
            )

            # 限制消息历史大小
            if len(state.messages) > 40:
                del state.messages[:-40]

            # 计算延迟
            latency_ms = round((perf_counter() - started_at) * 1000, 2)

            # 记录成功
            self._circuit_breaker.record_success()

            # 流式推送
            await self._emit_stream_deltas(
                trace_callback=trace_callback,
                trace_context=trace_context,
                session_id=session_id,
                model_name=model_name,
                content=content,
            )

            # 发射完成事件
            response_refs = _build_llm_log_refs(
                session_id=session_id,
                trace_id=trace_id,
                agent_name=str(trace_context.get("agent_name") or agent or "llm_agent"),
                phase=str(trace_context.get("phase") or ""),
                stage=str(trace_context.get("stage") or ""),
                response=content,
            )
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_http_response",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "llm_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "endpoint": endpoint,
                    "status_code": 200,
                    "response_payload": {
                        "content_preview": content[:1500],
                        "content_length": len(content),
                        "structured": bool(structured),
                        **response_refs,
                    },
                    "latency_ms": latency_ms,
                    "trace_id": trace_id,
                    **response_refs,
                },
            )
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_call_completed",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "llm_agent",
                    "model": model_name,
                    "session_id": session_id,
                    "latency_ms": latency_ms,
                    "response_preview": content[:1500],
                    "structured": bool(structured),
                    "trace_id": trace_id,
                    **response_refs,
                },
            )

            logger.info(
                "llm_request_completed",
                backend="langgraph",
                model=model_name,
                session_id=session_id,
                trace_id=trace_id,
                latency_ms=latency_ms,
                response_preview=self._truncate_text(content, 1200),
                response_ref=response_refs.get("response_ref"),
                full_response_logging=bool(settings.LLM_LOG_FULL_RESPONSE),
                structured=bool(structured),
            )
            if settings.LLM_LOG_FULL_RESPONSE:
                logger.info(
                    "llm_request_response_full",
                    backend="langgraph",
                    model=model_name,
                    session_id=session_id,
                    trace_id=trace_id,
                    phase=trace_context.get("phase"),
                    stage=trace_context.get("stage"),
                    response_ref=response_refs.get("response_ref"),
                    structured=bool(structured),
                    **_build_full_log_fields(response=content),
                )

            return {
                "content": content,
                "structured": structured,
                "info": {
                    "provider": "langgraph",
                    "model": model_name,
                    "session_id": state.id,
                    "endpoint": endpoint,
                    "structured": structured,
                    "structured_output": structured,
                    "trace_id": trace_id,
                },
            }

        except Exception as exc:
            # 记录失败
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
                    "agent_name": trace_context.get("agent_name") or agent or "llm_agent",
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
                    "type": "llm_call_timeout" if is_timeout else "llm_call_failed",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or agent or "llm_agent",
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
                backend="langgraph",
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
        """
        发射流式增量

        将响应内容分块推送给前端。

        Args:
            trace_callback: 追踪回调
            trace_context: 追踪上下文
            session_id: 会话 ID
            model_name: 模型名称
            content: 响应内容
        """
        text = (content or "").strip()
        if not text:
            return

        # 分块
        chunks = [text[i : i + self._STREAM_CHUNK_SIZE] for i in range(0, len(text), self._STREAM_CHUNK_SIZE)]
        truncated = False
        if len(chunks) > self._STREAM_MAX_CHUNKS:
            chunks = chunks[: self._STREAM_MAX_CHUNKS]
            truncated = True

        stream_id = f"{session_id}:{trace_context.get('agent_name') or 'llm_agent'}"

        for index, chunk in enumerate(chunks, start=1):
            await self._emit_trace_event(
                trace_callback,
                {
                    "type": "llm_stream_delta",
                    "phase": trace_context.get("phase"),
                    "stage": trace_context.get("stage"),
                    "agent_name": trace_context.get("agent_name") or "llm_agent",
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
        """
        发送文本提示词

        简化的文本提示词发送方法。

        Args:
            session_id: 会话 ID
            text: 文本内容
            model: 模型配置
            agent: Agent 名称
            format: 输出格式配置

        Returns:
            Dict[str, Any]: 响应结果
        """
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
        """
        发送结构化提示词

        要求 LLM 输出符合指定 JSON Schema 的结果。

        Args:
            session_id: 会话 ID
            text: 文本内容
            schema: JSON Schema
            model: 模型配置
            agent: Agent 名称

        Returns:
            Dict[str, Any]: 响应结果，structured 字段包含解析后的 JSON
        """
        return await self.send_prompt(
            session_id=session_id,
            parts=[{"type": "text", "text": text}],
            model=model,
            agent=agent,
            format={"type": "json_schema", "schema": schema},
        )

    async def run_command(self, session_id: str, command: str) -> Dict[str, Any]:
        """
        运行命令（不支持）

        Args:
            session_id: 会话 ID
            command: 命令

        Raises:
            NotImplementedError: 始终抛出
        """
        _ = (session_id, command)
        raise NotImplementedError("run_command is not supported")

    async def run_shell(self, session_id: str, command: str) -> Dict[str, Any]:
        """
        运行 Shell 命令（不支持）

        Args:
            session_id: 会话 ID
            command: 命令

        Raises:
            NotImplementedError: 始终抛出
        """
        _ = (session_id, command)
        raise NotImplementedError("run_shell is not supported")


# 全局客户端实例
_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """
    获取 LLM 客户端单例

    Returns:
        LLMClient: LLM 客户端实例
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance


async def create_llm_session(title: str) -> SessionInfo:
    """
    创建 LLM 会话

    便捷函数，用于快速创建会话。

    Args:
        title: 会话标题

    Returns:
        SessionInfo: 会话信息
    """
    client = get_llm_client()
    return await client.create_session(title=title)


# 全局客户端引用
llm_client = get_llm_client()
