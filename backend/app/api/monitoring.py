"""页面自动巡检 API。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.monitoring import MonitorTarget, MonitorTargetCreate, MonitorTargetUpdate, PageMonitorFinding
from app.services.page_monitoring_service import page_monitoring_service

router = APIRouter()


class MonitorStatusResponse(BaseModel):
    """巡检服务状态响应。"""

    running: bool
    tick_seconds: int
    active_targets: int
    last_loop_at: str = ""


class MonitorScanResponse(BaseModel):
    """手动巡检响应。"""

    finding: PageMonitorFinding


class MonitorEventListResponse(BaseModel):
    """巡检事件列表响应。"""

    items: List[Dict[str, Any]]


@router.get("/status", response_model=MonitorStatusResponse, summary="巡检状态")
async def get_monitoring_status() -> MonitorStatusResponse:
    status_value = await page_monitoring_service.status()
    return MonitorStatusResponse(
        running=status_value.running,
        tick_seconds=status_value.tick_seconds,
        active_targets=status_value.active_targets,
        last_loop_at=status_value.last_loop_at.isoformat() if status_value.last_loop_at else "",
    )


@router.post("/control/start", summary="启动巡检服务")
async def start_monitoring() -> Dict[str, str]:
    await page_monitoring_service.start()
    return {"status": "running"}


@router.post("/control/stop", summary="停止巡检服务")
async def stop_monitoring() -> Dict[str, str]:
    await page_monitoring_service.stop()
    return {"status": "stopped"}


@router.get("/targets", response_model=List[MonitorTarget], summary="巡检目标列表")
async def list_monitor_targets(enabled_only: bool = Query(False, description="仅返回启用目标")) -> List[MonitorTarget]:
    return await page_monitoring_service.list_targets(enabled_only=enabled_only)


@router.post("/targets", response_model=MonitorTarget, status_code=status.HTTP_201_CREATED, summary="创建巡检目标")
async def create_monitor_target(payload: MonitorTargetCreate) -> MonitorTarget:
    return await page_monitoring_service.create_target(payload)


@router.put("/targets/{target_id}", response_model=MonitorTarget, summary="更新巡检目标")
async def update_monitor_target(target_id: str, payload: MonitorTargetUpdate) -> MonitorTarget:
    target = await page_monitoring_service.update_target(target_id, payload)
    if not target:
        raise HTTPException(status_code=404, detail=f"monitor target {target_id} not found")
    return target


@router.delete("/targets/{target_id}", summary="删除巡检目标")
async def delete_monitor_target(target_id: str) -> Dict[str, Any]:
    deleted = await page_monitoring_service.delete_target(target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"monitor target {target_id} not found")
    return {"deleted": True}


@router.post("/targets/{target_id}/scan", response_model=MonitorScanResponse, summary="手动执行一次巡检")
async def scan_monitor_target(target_id: str) -> MonitorScanResponse:
    finding = await page_monitoring_service.scan_target_once(target_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"monitor target {target_id} not found")
    return MonitorScanResponse(finding=finding)


@router.get("/targets/{target_id}/events", response_model=MonitorEventListResponse, summary="查询巡检事件")
async def list_monitor_events(target_id: str, limit: int = Query(50, ge=1, le=200)) -> MonitorEventListResponse:
    items = await page_monitoring_service.list_events(target_id, limit=limit)
    return MonitorEventListResponse(items=items)

