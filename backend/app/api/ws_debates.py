"""
辩论 WebSocket
Debate WebSocket Endpoint
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.security import decode_token
from app.models.incident import IncidentStatus, IncidentUpdate
from app.services.debate_service import debate_service
from app.services.incident_service import incident_service

router = APIRouter()


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


ws_manager = DebateWebSocketManager()


async def _run_debate_with_events(session_id: str):
    async def _forward_event(event: Dict[str, Any]):
        await ws_manager.broadcast(session_id, {"type": "event", "data": event})

    session = await debate_service.get_session(session_id)
    if not session:
        await ws_manager.broadcast(
            session_id,
            {"type": "error", "message": f"Debate session {session_id} not found"},
        )
        return

    try:
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
    except Exception as e:
        latest = await debate_service.get_session(session_id)
        if latest:
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
                    },
                },
            )
        await ws_manager.broadcast(session_id, {"type": "error", "message": str(e)})


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

        await websocket.send_json(
            {
                "type": "snapshot",
                "data": {
                    "session_id": session.id,
                    "incident_id": session.incident_id,
                    "status": session.status.value,
                    "current_round": session.current_round,
                    "rounds": [r.model_dump(mode="json") for r in session.rounds],
                },
            }
        )

        auto_start = websocket.query_params.get("auto_start", "true").lower() == "true"
        if auto_start and session.status.value in {"pending", "analyzing", "debating"}:
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
            elif message == "snapshot":
                latest = await debate_service.get_session(session_id)
                if latest:
                    await websocket.send_json(
                        {
                            "type": "snapshot",
                            "data": {
                                "session_id": latest.id,
                                "status": latest.status.value,
                                "current_round": latest.current_round,
                                "rounds": [r.model_dump(mode="json") for r in latest.rounds],
                            },
                        }
                    )

    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(session_id, websocket)
