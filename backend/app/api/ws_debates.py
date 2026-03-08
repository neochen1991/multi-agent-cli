"""
辩论 WebSocket 模块

本模块实现了辩论会话的 WebSocket 实时通信功能：
1. 客户端连接管理：支持多客户端同时连接同一会话
2. 实时事件推送：将 Agent 执行过程实时推送到前端
3. 会话控制：支持启动、暂停、恢复、取消等操作
4. 状态同步：定期推送会话快照，确保前后端状态一致

WebSocket 消息类型：
- ping/pong: 心跳检测
- start: 启动辩论
- resume: 恢复辩论
- cancel: 取消辩论
- snapshot: 请求状态快照

事件类型：
- agent_chat: Agent 输出消息
- tool_io: 工具调用输入/输出
- phase: 阶段变更
- result: 最终结果
- error: 错误信息

Debate WebSocket Endpoint
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from app.config import settings
from app.core.event_schema import enrich_event, new_trace_id
from app.core.security import decode_token
from app.models.incident import IncidentStatus, IncidentUpdate
from app.runtime.task_registry import runtime_task_registry
from app.services.debate_service import HumanReviewRequired, debate_service
from app.services.incident_service import incident_service

router = APIRouter()
logger = structlog.get_logger()


class DebateWebSocketManager:
    """
    WebSocket 连接管理器

    负责管理辩论会话的 WebSocket 连接：
    - 维护会话 ID 到连接列表的映射
    - 支持同一会话的多客户端连接
    - 管理后台任务的生命周期

    Attributes:
        _connections: 会话 ID 到 WebSocket 连接列表的映射
        _running_tasks: 会话 ID 到正在运行的 asyncio.Task 的映射
    """

    def __init__(self):
        """初始化连接管理器"""
        # 会话 ID -> WebSocket 连接列表
        self._connections: Dict[str, List[WebSocket]] = {}
        # 会话 ID -> 正在运行的辩论任务
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        """
        接受新的 WebSocket 连接

        Args:
            session_id: 辩论会话 ID
            websocket: WebSocket 连接实例
        """
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        """
        断开 WebSocket 连接

        从连接列表中移除指定的连接，如果会话没有其他连接则清理映射。

        Args:
            session_id: 辩论会话 ID
            websocket: 要断开的 WebSocket 连接
        """
        clients = self._connections.get(session_id, [])
        if websocket in clients:
            clients.remove(websocket)
        # 如果没有剩余连接，清理该会话的映射
        if not clients and session_id in self._connections:
            self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, payload: Dict[str, Any]):
        """
        向会话的所有连接广播消息

        Args:
            session_id: 辩论会话 ID
            payload: 要发送的消息载荷
        """
        clients = list(self._connections.get(session_id, []))
        for client in clients:
            try:
                await client.send_json(payload)
            except Exception:
                # 发送失败时断开连接
                self.disconnect(session_id, client)

    def get_running_task(self, session_id: str) -> asyncio.Task | None:
        """
        获取会话正在运行的辩论任务

        检查任务是否存在且仍在运行。

        Args:
            session_id: 辩论会话 ID

        Returns:
            asyncio.Task | None: 运行中的任务或 None
        """
        task = self._running_tasks.get(session_id)
        if task and task.done():
            # 任务已完成，清理映射
            self._running_tasks.pop(session_id, None)
            return None
        return task

    def ensure_running(self, session_id: str, coro_factory) -> asyncio.Task:
        """
        确保会话有正在运行的辩论任务

        如果任务已存在且运行中，直接返回；否则创建新任务。

        Args:
            session_id: 辩论会话 ID
            coro_factory: 创建协程的工厂函数（无参）

        Returns:
            asyncio.Task: 运行中的任务
        """
        task = self.get_running_task(session_id)
        if task:
            return task

        # 创建新任务
        task = asyncio.create_task(coro_factory())
        self._running_tasks[session_id] = task

        def _cleanup(done_task: asyncio.Task) -> None:
            """任务完成时的清理回调"""
            current = self._running_tasks.get(session_id)
            if current is done_task:
                self._running_tasks.pop(session_id, None)

        task.add_done_callback(_cleanup)
        return task

    def cancel_running(self, session_id: str) -> bool:
        """
        取消会话正在运行的辩论任务

        Args:
            session_id: 辩论会话 ID

        Returns:
            bool: 是否成功取消了任务
        """
        task = self.get_running_task(session_id)
        if not task:
            return False
        task.cancel()
        return True


# 全局 WebSocket 管理器实例
ws_manager = DebateWebSocketManager()


def _build_ws_control_event(
    *,
    session_id: str,
    trace_id: str,
    event_type: str,
    phase: str,
    message: str = "",
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    构建 WebSocket 控制事件

    创建标准格式的事件载荷，用于控制消息（如 pong、ack、error）。

    Args:
        session_id: 辩论会话 ID
        trace_id: 追踪 ID，用于日志关联
        event_type: 事件类型（如 ws_pong、ws_ack、ws_error）
        phase: 当前阶段
        message: 可选的消息内容
        extra: 可选的额外字段

    Returns:
        Dict[str, Any]: 事件载荷
    """
    payload: Dict[str, Any] = {
        "type": event_type,
        "phase": phase,
        "session_id": session_id,
    }
    if message:
        payload["message"] = message
    if extra:
        payload.update(extra)
    # 使用 enrich_event 添加标准字段（trace_id、timestamp 等）
    return enrich_event(
        payload,
        trace_id=trace_id,
        default_phase=phase,
    )


async def _build_session_snapshot(session_id: str, session=None) -> Dict[str, Any] | None:
    """构建当前会话快照。

    快照会同时带上 rounds、任务状态和人工审核状态，供前端在刷新或重连时快速恢复界面。"""
    latest = session or await debate_service.get_session(session_id)
    if not latest:
        return None
    task_state = await runtime_task_registry.get(session_id)
    human_review = (latest.context or {}).get("human_review")
    return enrich_event(
        {
            "type": "snapshot",
            "phase": str(latest.current_phase.value if latest.current_phase else latest.status.value),
            "session_id": latest.id,
            "incident_id": latest.incident_id,
            "status": latest.status.value,
            "current_round": latest.current_round,
            "rounds": [r.model_dump(mode="json") for r in latest.rounds],
            "task_state": task_state.to_dict() if task_state else None,
            "human_review": human_review if isinstance(human_review, dict) else None,
        },
        trace_id=str((latest.context or {}).get("trace_id") or ""),
        default_phase="snapshot",
    )


async def _broadcast_latest_review_event(session_id: str) -> None:
    """广播最近一条人工审核事件，保持多个客户端之间的审核状态同步。"""
    latest = await debate_service.get_session(session_id)
    if not latest:
        return
    event_log = (latest.context or {}).get("event_log")
    if not isinstance(event_log, list) or not event_log:
        return
    last = event_log[-1]
    event = last.get("event") if isinstance(last, dict) else None
    if not isinstance(event, dict):
        return
    if not str(event.get("type") or "").startswith("human_review_"):
        return
    await ws_manager.broadcast(session_id, {"type": "event", "data": event})


async def _run_debate_with_events(session_id: str):
    """
    运行辩论并实时推送事件

    这是 WebSocket 辩论的核心执行函数：
    1. 从事件流中转发 Agent 执行过程
    2. 处理成功、取消、错误三种结束状态
    3. 更新 Incident 状态和结果

    Args:
        session_id: 辩论会话 ID
    """
    async def _forward_event(event: Dict[str, Any]):
        """
        事件转发回调

        将辩论过程中的事件广播到 WebSocket，同时更新心跳。

        Args:
            event: 事件数据
        """
        # 更新任务心跳，用于恢复时定位断点
        await runtime_task_registry.mark_heartbeat(
            session_id,
            phase=str(event.get("phase") or ""),
            event_type=str(event.get("type") or ""),
            round_number=(
                int(event.get("round_number"))
                if isinstance(event.get("round_number"), (int, float, str)) and str(event.get("round_number")).isdigit()
                else None
            ),
        )
        # 广播事件到所有连接的客户端
        await ws_manager.broadcast(session_id, {"type": "event", "data": event})

    # 获取会话信息
    session = await debate_service.get_session(session_id)
    if not session:
        # 会话不存在，发送错误事件
        event = _build_ws_control_event(
            session_id=session_id,
            trace_id=new_trace_id("deb"),
            event_type="ws_error",
            phase="failed",
            message=f"Debate session {session_id} not found",
        )
        await ws_manager.broadcast(
            session_id,
            {
                "type": "error",
                "message": f"Debate session {session_id} not found",
                "data": event,
                **event,
            },
        )
        return

    try:
        # 统一 trace_id，确保 ws 控制事件与辩论轨迹可以关联检索。
        trace_id = str((session.context or {}).get("trace_id") or "").strip()
        if not trace_id:
            trace_id = new_trace_id("deb")
        # 进入运行态后先登记到任务注册表，便于断线恢复与状态查询。
        await runtime_task_registry.mark_started(
            session_id=session_id,
            task_type="debate",
            trace_id=trace_id,
        )
        # 把事件回调传入 DebateService，用于实时转发运行轨迹。
        result = await debate_service.execute_debate(session_id, event_callback=_forward_event)
        # 成功完成后把结果同步回 incident，保证列表页和详情页状态一致。
        await incident_service.update_incident(
            session.incident_id,
            IncidentUpdate(
                status=IncidentStatus.RESOLVED,
                root_cause=result.root_cause,
                fix_suggestion=(
                    result.fix_recommendation.summary if result.fix_recommendation else None
                ),
                impact_analysis=(
                    result.impact_analysis.model_dump() if result.impact_analysis else None
                ),
            ),
        )
        # 单独推送 result_ready 事件，让前端在不刷新详情的情况下知道结果已产出。
        result_event = enrich_event(
            {
                "type": "result_ready",
                "phase": "completed",
                "session_id": result.session_id,
                "incident_id": result.incident_id,
                "root_cause": result.root_cause,
                "confidence": result.confidence,
                "created_at": result.created_at.isoformat(),
            },
            trace_id=trace_id,
            default_phase="completed",
        )
        await ws_manager.broadcast(session_id, {"type": "result", "data": result_event})
        await runtime_task_registry.mark_done(session_id, status="completed")
    except HumanReviewRequired as review_exc:
        # 命中图内人工审核时进入 waiting_review，而不是走失败分支。
        await runtime_task_registry.mark_waiting_review(
            session_id,
            review_reason=review_exc.reason,
            resume_from_step=review_exc.resume_from_step,
            phase="waiting_review",
            event_type="human_review_requested",
        )
        snapshot = await _build_session_snapshot(session_id)
        if snapshot:
            await ws_manager.broadcast(session_id, {"type": "snapshot", "data": snapshot})
    except asyncio.CancelledError:
        # 处理取消请求
        await debate_service.cancel_session(session_id, reason="ws_cancel")
        if session and session.incident_id:
            await incident_service.update_incident(
                session.incident_id,
                IncidentUpdate(
                    status=IncidentStatus.CLOSED,
                    fix_suggestion="analysis cancelled",
                ),
            )
        await runtime_task_registry.mark_done(session_id, status="cancelled")
        await ws_manager.broadcast(
            session_id,
            {
                "type": "event",
                "data": enrich_event(
                    {
                        "type": "session_cancelled",
                        "session_id": session_id,
                        "phase": "cancelled",
                        "status": "cancelled",
                    },
                    trace_id=trace_id,
                    default_phase="cancelled",
                ),
            },
        )
    except Exception as e:
        # 普通异常会进入 failed，并补充快照与错误事件，方便前端定位失败位置。
        await runtime_task_registry.mark_done(session_id, status="failed", error=str(e))
        logger.error("ws_debate_task_failed", session_id=session_id, error=str(e))
        # 重新获取最新 session，避免继续使用进入异常前的旧对象。
        latest = await debate_service.get_session(session_id)
        # 这些 last_error_* 字段由 runtime 写入，用于告诉前端错误是否可恢复。
        error_code = ""
        recoverable = False
        retry_hint = ""
        if latest and isinstance(latest.context, dict):
            error_code = str(latest.context.get("last_error_code") or "")
            recoverable = bool(latest.context.get("last_error_recoverable") or False)
            retry_hint = str(latest.context.get("last_error_retry_hint") or "")
        # 先发 snapshot 再发 error，前端才能同时拿到最新 rounds 和失败状态。
        if latest:
            task_state = await runtime_task_registry.get(session_id)
            snapshot = enrich_event(
                {
                    "type": "snapshot",
                    "phase": str(latest.current_phase.value if latest.current_phase else latest.status.value),
                    "session_id": latest.id,
                    "incident_id": latest.incident_id,
                    "status": latest.status.value,
                    "current_round": latest.current_round,
                    "rounds": [r.model_dump(mode="json") for r in latest.rounds],
                    "task_state": task_state.to_dict() if task_state else None,
                },
                trace_id=str((latest.context or {}).get("trace_id") or trace_id or ""),
                default_phase="snapshot",
            )
            await ws_manager.broadcast(session_id, {"type": "snapshot", "data": snapshot})
        # 错误统一包装为标准 ws_error 控制事件，方便前端按一种方式渲染。
        error_event = _build_ws_control_event(
            session_id=session_id,
            trace_id=trace_id,
            event_type="ws_error",
            phase="failed",
            message=str(e),
            extra={
                "error": str(e),
                "error_code": error_code,
                "recoverable": recoverable,
                "retry_hint": retry_hint,
            },
        )
        await ws_manager.broadcast(
            session_id,
            {
                "type": "error",
                "message": str(e),
                "error_code": error_code,
                "recoverable": recoverable,
                "retry_hint": retry_hint,
                "data": error_event,
                **error_event,
            },
        )


@router.websocket("/ws/debates/{session_id}")
async def debate_ws(websocket: WebSocket, session_id: str):
    """
    辩论 WebSocket 端点

    处理客户端的 WebSocket 连接，支持以下操作：
    - ping: 心跳检测，返回 pong
    - start: 启动辩论执行
    - resume: 恢复暂停的辩论
    - cancel: 取消正在运行的辩论
    - snapshot: 请求当前状态快照

    连接流程：
    1. 认证检查（如果启用）
    2. 加入会话连接池
    3. 发送初始快照
    4. 如果 auto_start=true 且会话正在运行，自动启动执行
    5. 进入消息循环，处理客户端命令

    Args:
        websocket: WebSocket 连接实例
        session_id: 辩论会话 ID
    """
    # 认证检查
    if settings.AUTH_ENABLED:
        token = websocket.query_params.get("token", "")
        if not token:
            await websocket.close(code=4401)  # Unauthorized
            return
        try:
            decode_token(token)
        except Exception:
            await websocket.close(code=4401)  # Unauthorized
            return

    # 接受连接并加入连接池
    await ws_manager.connect(session_id, websocket)
    running_task = ws_manager.get_running_task(session_id)
    try:
        # 建连后先读取会话，如果会话不存在则立即返回错误并关闭连接。
        session = await debate_service.get_session(session_id)
        if not session:
            # 会话不存在，发送错误并关闭连接
            error_event = _build_ws_control_event(
                session_id=session_id,
                trace_id=new_trace_id("deb"),
                event_type="ws_error",
                phase="failed",
                message=f"Debate session {session_id} not found",
            )
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Debate session {session_id} not found",
                    "data": error_event,
                    **error_event,
                }
            )
            await websocket.close(code=4404)  # Not Found
            return

        # 首次连接先发一份完整快照，避免前端等待后续事件才知道当前状态。
        snapshot = await _build_session_snapshot(session_id, session=session)
        if snapshot:
            await websocket.send_json({"type": "snapshot", "data": snapshot})

        # auto_start=true 时，如果会话仍处于运行态或任务注册表显示运行中，则自动拉起执行。
        auto_start = websocket.query_params.get("auto_start", "true").lower() == "true"
        review_state = (session.context or {}).get("human_review")
        review_status = (
            str(review_state.get("status") or "").strip().lower()
            if isinstance(review_state, dict)
            else ""
        )
        waiting_for_human_review = (
            session.status.value == "waiting" and review_status in {"pending", "approved"}
        )
        running_like_status = {"pending", "running", "analyzing", "debating", "retrying"}
        if session.status.value == "waiting" and not waiting_for_human_review:
            running_like_status.add("waiting")
        task_state = await runtime_task_registry.get(session_id)
        should_resume = bool(task_state and task_state.status == "running")
        if auto_start and (session.status.value in running_like_status or should_resume):
            running_task = ws_manager.ensure_running(
                session_id,
                lambda: _run_debate_with_events(session_id),
            )

        # 控制消息循环：这里只处理少数控制命令，真正执行业务逻辑仍在服务层/runtime。
        while True:
            message = await websocket.receive_text()

            if message == "ping":
                # 心跳检测：返回 pong
                pong_event = _build_ws_control_event(
                    session_id=session_id,
                    trace_id=str((session.context or {}).get("trace_id") or ""),
                    event_type="ws_pong",
                    phase="control",
                    message="pong",
                )
                await websocket.send_json({"type": "pong", "data": pong_event, **pong_event})

            elif message == "start":
                # 显式启动；若已有运行任务则直接复用，避免重复开跑。
                running_task = ws_manager.ensure_running(
                    session_id,
                    lambda: _run_debate_with_events(session_id),
                )

            elif message == "resume":
                # 恢复前先判断是否仍在等待人工审核，避免绕过审批继续执行。
                latest = await debate_service.get_session(session_id)
                review_state = (latest.context or {}).get("human_review") if latest else None
                review_status = (
                    str(review_state.get("status") or "").strip().lower()
                    if isinstance(review_state, dict)
                    else ""
                )
                if latest and latest.status.value == "waiting" and review_status == "pending":
                    ack = enrich_event(
                        {
                            "type": "ws_ack",
                            "phase": "control",
                            "session_id": session_id,
                            "message": "human review pending",
                        },
                        trace_id=str((latest.context or {}).get("trace_id") or ""),
                        default_phase="control",
                    )
                    await websocket.send_json(
                        {
                            "type": "ack",
                            "message": "human review pending",
                            "data": ack,
                            **ack,
                        }
                    )
                    continue
                running_task = ws_manager.ensure_running(
                    session_id,
                    lambda: _run_debate_with_events(session_id),
                )
                # ack 中带断点位置，前端可以展示“从哪里继续”。
                resume_task_state = await runtime_task_registry.get(session_id)
                ack = enrich_event(
                    {
                        "type": "ws_ack",
                        "phase": "control",
                        "session_id": session_id,
                        "message": "resume accepted",
                        "resume_from": {
                            "phase": str(resume_task_state.last_phase if resume_task_state else ""),
                            "event_type": str(resume_task_state.last_event_type if resume_task_state else ""),
                            "round": int(resume_task_state.last_round if resume_task_state else 0),
                            "updated_at": str(resume_task_state.updated_at if resume_task_state else ""),
                        },
                    },
                    trace_id=str((session.context or {}).get("trace_id") or ""),
                    default_phase="control",
                )
                await websocket.send_json(
                    {
                        "type": "ack",
                        "message": "resume accepted",
                        "data": ack,
                        **ack,
                    }
                )

            elif message == "approve":
                # 审核批准后广播 review 事件和 snapshot，确保多个页面状态一致。
                approved = await debate_service.approve_human_review(session_id)
                ack_message = "review approved" if approved else "no pending review"
                if approved:
                    await runtime_task_registry.mark_review_decision(
                        session_id,
                        review_status="approved",
                        status="waiting_review",
                    )
                    await _broadcast_latest_review_event(session_id)
                    snapshot = await _build_session_snapshot(session_id)
                    if snapshot:
                        await ws_manager.broadcast(session_id, {"type": "snapshot", "data": snapshot})
                ack = enrich_event(
                    {
                        "type": "ws_ack",
                        "phase": "control",
                        "session_id": session_id,
                        "message": ack_message,
                    },
                    trace_id=str((session.context or {}).get("trace_id") or ""),
                    default_phase="control",
                )
                await websocket.send_json(
                    {
                        "type": "ack",
                        "message": ack_message,
                        "data": ack,
                        **ack,
                    }
                )

            elif message == "reject":
                # 审核驳回后同样广播最新 review 事件和 snapshot。
                rejected = await debate_service.reject_human_review(session_id)
                ack_message = "review rejected" if rejected else "no pending review"
                if rejected:
                    await runtime_task_registry.mark_review_decision(
                        session_id,
                        review_status="rejected",
                        status="failed",
                        error="human_review_rejected",
                    )
                    await _broadcast_latest_review_event(session_id)
                    snapshot = await _build_session_snapshot(session_id)
                    if snapshot:
                        await ws_manager.broadcast(session_id, {"type": "snapshot", "data": snapshot})
                ack = enrich_event(
                    {
                        "type": "ws_ack",
                        "phase": "control",
                        "session_id": session_id,
                        "message": ack_message,
                    },
                    trace_id=str((session.context or {}).get("trace_id") or ""),
                    default_phase="control",
                )
                await websocket.send_json(
                    {
                        "type": "ack",
                        "message": ack_message,
                        "data": ack,
                        **ack,
                    }
                )

            elif message == "cancel":
                # 取消时既要停掉运行任务，也要把 session/incident 状态推进到关闭态。
                cancelled = ws_manager.cancel_running(session_id)
                await debate_service.cancel_session(session_id, reason="ws_cancel")
                await incident_service.update_incident(
                    session.incident_id,
                    IncidentUpdate(
                        status=IncidentStatus.CLOSED,
                        fix_suggestion="analysis cancelled",
                    ),
                )
                ack_message = "cancel accepted" if cancelled else "no running task"
                ack = enrich_event(
                    {
                        "type": "ws_ack",
                        "phase": "control",
                        "session_id": session_id,
                        "message": ack_message,
                    },
                    trace_id=str((session.context or {}).get("trace_id") or ""),
                    default_phase="control",
                )
                await websocket.send_json(
                    {
                        "type": "ack",
                        "message": ack_message,
                        "data": ack,
                        **ack,
                    }
                )

            elif message == "snapshot":
                # 前端主动请求快照时，总是重新计算最新状态而不是复用旧数据。
                snapshot = await _build_session_snapshot(session_id)
                if snapshot:
                    await websocket.send_json({"type": "snapshot", "data": snapshot})

    except WebSocketDisconnect:
        # 客户端主动断开连接
        pass
    finally:
        # 清理连接
        ws_manager.disconnect(session_id, websocket)
