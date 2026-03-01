"""
辩论 WebSocket
Debate WebSocket Endpoint
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from app.config import settings
from app.core.security import decode_token
from app.models.incident import IncidentStatus, IncidentUpdate
from app.runtime.task_registry import runtime_task_registry
from app.services.debate_service import debate_service
from app.services.incident_service import incident_service

router = APIRouter()
logger = structlog.get_logger()


class DebateWebSocketManager:
    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        clients = self._connections.get(session_id, [])
        if websocket in clients:
            clients.remove(websocket)
        if not clients and session_id in self._connections:
            self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, payload: Dict[str, Any]):
        clients = list(self._connections.get(session_id, []))
        for client in clients:
            try:
                await client.send_json(payload)
            except Exception:
                self.disconnect(session_id, client)

    def get_running_task(self, session_id: str) -> asyncio.Task | None:
        task = self._running_tasks.get(session_id)
        if task and task.done():
            self._running_tasks.pop(session_id, None)
            return None
        return task

    def ensure_running(self, session_id: str, coro_factory) -> asyncio.Task:
        task = self.get_running_task(session_id)
        if task:
            return task

        task = asyncio.create_task(coro_factory())
        self._running_tasks[session_id] = task

        def _cleanup(done_task: asyncio.Task) -> None:
            current = self._running_tasks.get(session_id)
            if current is done_task:
                self._running_tasks.pop(session_id, None)

        task.add_done_callback(_cleanup)
        return task

    def cancel_running(self, session_id: str) -> bool:
        task = self.get_running_task(session_id)
        if not task:
            return False
        task.cancel()
        return True


ws_manager = DebateWebSocketManager()


async def _run_debate_with_events(session_id: str):
    async def _forward_event(event: Dict[str, Any]):
        await runtime_task_registry.mark_heartbeat(session_id)
        await ws_manager.broadcast(session_id, {"type": "event", "data": event})

    session = await debate_service.get_session(session_id)
    if not session:
        await ws_manager.broadcast(
            session_id,
            {"type": "error", "message": f"Debate session {session_id} not found"},
        )
        return

    try:
        trace_id = str((session.context or {}).get("trace_id") or "").strip()
        await runtime_task_registry.mark_started(
            session_id=session_id,
            task_type="debate",
            trace_id=trace_id,
        )
        result = await debate_service.execute_debate(session_id, event_callback=_forward_event)
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
        await ws_manager.broadcast(
            session_id,
            {
                "type": "result",
                "data": {
                    "session_id": result.session_id,
                    "incident_id": result.incident_id,
                    "root_cause": result.root_cause,
                    "confidence": result.confidence,
                    "created_at": result.created_at.isoformat(),
                },
            },
        )
        await runtime_task_registry.mark_done(session_id, status="completed")
    except asyncio.CancelledError:
        await debate_service.cancel_session(session_id, reason="ws_cancel")
        await runtime_task_registry.mark_done(session_id, status="cancelled")
        await ws_manager.broadcast(
            session_id,
            {
                "type": "event",
                "data": {
                    "type": "session_cancelled",
                    "session_id": session_id,
                    "phase": "cancelled",
                    "status": "cancelled",
                },
            },
        )
    except Exception as e:
        await runtime_task_registry.mark_done(session_id, status="failed", error=str(e))
        logger.error("ws_debate_task_failed", session_id=session_id, error=str(e))
        latest = await debate_service.get_session(session_id)
        error_code = ""
        recoverable = False
        retry_hint = ""
        if latest and isinstance(latest.context, dict):
            error_code = str(latest.context.get("last_error_code") or "")
            recoverable = bool(latest.context.get("last_error_recoverable") or False)
            retry_hint = str(latest.context.get("last_error_retry_hint") or "")
        if latest:
            task_state = await runtime_task_registry.get(session_id)
            await ws_manager.broadcast(
                session_id,
                {
                    "type": "snapshot",
                    "data": {
                        "session_id": latest.id,
                        "incident_id": latest.incident_id,
                        "status": latest.status.value,
                        "current_round": latest.current_round,
                        "rounds": [r.model_dump(mode="json") for r in latest.rounds],
                        "task_state": task_state.to_dict() if task_state else None,
                    },
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
            },
        )


@router.websocket("/ws/debates/{session_id}")
async def debate_ws(websocket: WebSocket, session_id: str):
    if settings.AUTH_ENABLED:
        token = websocket.query_params.get("token", "")
        if not token:
            await websocket.close(code=4401)
            return
        try:
            decode_token(token)
        except Exception:
            await websocket.close(code=4401)
            return

    await ws_manager.connect(session_id, websocket)
    running_task = ws_manager.get_running_task(session_id)
    try:
        session = await debate_service.get_session(session_id)
        if not session:
            await websocket.send_json(
                {"type": "error", "message": f"Debate session {session_id} not found"}
            )
            await websocket.close(code=4404)
            return

        task_state = await runtime_task_registry.get(session_id)
        await websocket.send_json(
            {
                "type": "snapshot",
                "data": {
                    "session_id": session.id,
                    "incident_id": session.incident_id,
                    "status": session.status.value,
                    "current_round": session.current_round,
                    "rounds": [r.model_dump(mode="json") for r in session.rounds],
                    "task_state": task_state.to_dict() if task_state else None,
                },
            }
        )

        auto_start = websocket.query_params.get("auto_start", "true").lower() == "true"
        running_like_status = {"pending", "running", "analyzing", "debating", "waiting", "retrying"}
        should_resume = bool(task_state and task_state.status == "running")
        if auto_start and (session.status.value in running_like_status or should_resume):
            running_task = ws_manager.ensure_running(
                session_id,
                lambda: _run_debate_with_events(session_id),
            )

        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
            elif message == "start":
                running_task = ws_manager.ensure_running(
                    session_id,
                    lambda: _run_debate_with_events(session_id),
                )
            elif message == "resume":
                running_task = ws_manager.ensure_running(
                    session_id,
                    lambda: _run_debate_with_events(session_id),
                )
                await websocket.send_json({"type": "ack", "message": "resume accepted"})
            elif message == "cancel":
                cancelled = ws_manager.cancel_running(session_id)
                await debate_service.cancel_session(session_id, reason="ws_cancel")
                await websocket.send_json(
                    {
                        "type": "ack",
                        "message": "cancel accepted" if cancelled else "no running task",
                    }
                )
            elif message == "snapshot":
                latest = await debate_service.get_session(session_id)
                if latest:
                    task_state = await runtime_task_registry.get(session_id)
                    await websocket.send_json(
                        {
                            "type": "snapshot",
                            "data": {
                                "session_id": latest.id,
                                "status": latest.status.value,
                                "current_round": latest.current_round,
                                "rounds": [r.model_dump(mode="json") for r in latest.rounds],
                                "task_state": task_state.to_dict() if task_state else None,
                            },
                        }
                    )

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(session_id, websocket)
