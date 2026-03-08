"""
事件分发器模块

本模块提供运行时事件的持久化和转发功能。

事件流设计：
1. Agent 执行产生事件 -> emit() -> 持久化 + 回调转发
2. 事件被记录到 runtime_session_store 用于断点恢复
3. 事件被记录到 lineage_recorder 用于审计追踪
4. 事件通过回调转发给 WebSocket 客户端

事件类型：
- agent: Agent 执行事件
- tool: 工具调用事件
- event: 其他事件

Event dispatching utilities for LangGraph runtime.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.event_schema import enrich_event
from app.runtime.langgraph.output_truncation import output_reference_store
from app.runtime.session_store import runtime_session_store
from app.runtime.trace_lineage import lineage_recorder


class EventDispatcher:
    """
    事件分发器

    负责事件的持久化和转发：
    1. 持久化事件到 session store
    2. 记录事件到审计轨迹
    3. 通过回调转发事件给客户端

    属性：
    - _trace_id: 追踪 ID
    - _session_id: 会话 ID
    - _callback: 事件回调函数
    - _event_sequence: 事件序号计数器
    """

    def __init__(
        self,
        *,
        trace_id: str = "",
        session_id: str = "",
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        """
        初始化事件分发器

        Args:
            trace_id: 追踪 ID，用于日志关联
            session_id: 会话 ID
            callback: 事件回调函数（异步）
        """
        self._trace_id = str(trace_id or "")
        self._session_id = str(session_id or "")
        self._callback = callback
        self._event_sequence = 0

    def bind(
        self,
        *,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        """
        绑定运行时上下文

        在会话开始时绑定 trace_id、session_id 和回调函数。
        如果 session_id 变化，重置事件序号计数器。

        Args:
            trace_id: 追踪 ID
            session_id: 会话 ID
            callback: 事件回调函数
        """
        if trace_id is not None:
            self._trace_id = str(trace_id or "")
        if session_id is not None:
            next_session = str(session_id or "")
            if next_session != self._session_id:
                # 会话变化时重置序号
                self._event_sequence = 0
            self._session_id = next_session
        if callback is not None:
            self._callback = callback

    async def emit(self, event: Dict[str, Any]) -> None:
        """
        发射事件

        处理事件发射的完整流程：
        1. 递增事件序号
        2. 补充 session_id
        3. 通过 enrich_event 添加标准字段
        4. 持久化到 session store
        5. 记录到审计轨迹
        6. 通过回调转发

        Args:
            event: 事件数据字典
        """
        self._event_sequence += 1
        outbound = dict(event or {})
        outbound.setdefault("event_sequence", self._event_sequence)
        if self._session_id and "session_id" not in outbound:
            outbound["session_id"] = self._session_id
        # 添加标准字段（trace_id、timestamp 等）
        payload = enrich_event(
            outbound,
            trace_id=self._trace_id or None,
            default_phase=str(outbound.get("phase") or ""),
        )
        # 持久化到会话存储
        await runtime_session_store.append_event(
            self._session_id or "unknown",
            payload,
        )
        # 记录到审计轨迹
        await self._append_lineage(payload)
        # 通过回调转发
        if not self._callback:
            return
        maybe = self._callback(payload)
        if asyncio.iscoroutine(maybe):
            await maybe

    async def _append_lineage(self, payload: Dict[str, Any]) -> None:
        """
        追加审计轨迹

        将事件记录到审计轨迹，用于问题排查和历史回溯。

        Args:
            payload: 事件数据
        """
        session_id = str(payload.get("session_id") or self._session_id or "unknown")
        event_type = str(payload.get("type") or "")
        phase = str(payload.get("phase") or "")
        agent_name = str(payload.get("agent_name") or "")

        # 提取输出摘要
        output_summary = {}
        if isinstance(payload.get("output_json"), dict):
            output = payload.get("output_json") or {}
            output_summary = {
                "conclusion": str(output.get("conclusion") or "")[:260],
                "confidence": float(output.get("confidence") or 0.0),
            }

        # 提取输入摘要
        input_summary = {}
        if "prompt_length" in payload or "prompt_preview" in payload:
            input_summary = {
                "prompt_length": int(payload.get("prompt_length") or 0),
                "prompt_preview": str(payload.get("prompt_preview") or "")[:320],
            }

        # 确定事件类型
        kind = "event"
        if event_type in {"agent_round", "agent_chat_message"}:
            kind = "agent"
        elif event_type.startswith("tool_") or "tool" in event_type:
            kind = "tool"

        # 构建工具审计信息
        tool_audit = self._build_tool_audit(payload) if kind == "tool" else {}

        # 记录到审计轨迹
        await lineage_recorder.append(
            session_id=session_id,
            trace_id=str(payload.get("trace_id") or self._trace_id or ""),
            kind=kind,
            phase=phase,
            agent_name=agent_name,
            event_type=event_type,
            confidence=float(payload.get("confidence") or 0.0),
            duration_ms=float(payload.get("latency_ms") or 0.0),
            input_summary=input_summary,
            output_summary=output_summary,
            payload={
                "event_id": payload.get("event_id"),
                "event_sequence": payload.get("event_sequence"),
                "message": str(payload.get("message") or "")[:240],
                **tool_audit,
            },
        )

    def _build_tool_audit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建工具审计信息

        从事件数据中提取工具调用的审计信息，包括：
        - 工具名称
        - 请求参数
        - 响应数据
        - 执行状态
        - 耗时

        对于过大的响应数据，会存储到 output_reference_store 并返回引用。

        Args:
            payload: 事件数据

        Returns:
            Dict[str, Any]: 工具审计信息
        """
        tool_name = str(payload.get("tool_name") or payload.get("name") or "").strip()
        status = str(payload.get("status") or payload.get("io_status") or "").strip() or "unknown"
        duration_ms = float(payload.get("latency_ms") or payload.get("duration_ms") or 0.0)
        error_text = str(payload.get("error") or payload.get("error_message") or "").strip()

        # 请求信息
        request = {
            "command_gate": payload.get("command_gate") if isinstance(payload.get("command_gate"), dict) else {},
            "io_action": payload.get("io_action"),
            "phase": payload.get("phase"),
        }

        # 响应信息
        response = {}
        if isinstance(payload.get("data_preview"), dict):
            response["data_preview"] = payload.get("data_preview")
        if isinstance(payload.get("data_detail"), dict):
            response["data_detail"] = payload.get("data_detail")
        if isinstance(payload.get("io_detail"), dict):
            response["io_detail"] = payload.get("io_detail")

        # 处理过大的响应数据
        output_ref = ""
        if response:
            try:
                serialized = json.dumps(response, ensure_ascii=False)
            except Exception:
                serialized = ""
            if len(serialized) > 1800:
                # 存储到引用存储，返回引用 ID
                output_ref = output_reference_store.save(
                    content=serialized,
                    session_id=str(payload.get("session_id") or self._session_id or ""),
                    category="tool_audit",
                    metadata={
                        "tool_name": tool_name,
                        "event_type": str(payload.get("type") or ""),
                    },
                )
                response = {"truncated": True, "output_ref": output_ref}

        return {
            "tool_name": tool_name,
            "request": request,
            "response": response,
            "status": status,
            "duration_ms": duration_ms,
            "error": error_text,
            "ref_id": output_ref,
            "execution_path": str(payload.get("execution_path") or ""),
            "permission": payload.get("permission_decision") or {},
        }


__all__ = ["EventDispatcher"]
