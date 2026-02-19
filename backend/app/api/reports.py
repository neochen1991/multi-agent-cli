"""
报告 API
Report API Endpoints
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.report_service import report_service

router = APIRouter()


class ReportResponse(BaseModel):
    """报告响应"""

    report_id: str
    incident_id: str
    debate_session_id: Optional[str] = None
    format: str
    content: str
    file_path: Optional[str] = None
    generated_at: datetime


class ReportExportRequest(BaseModel):
    """报告导出请求"""

    format: str = Field(
        default="json",
        pattern="^(json|markdown|html|pdf)$",
        description="导出格式",
    )
    include_details: bool = Field(default=True, description="是否包含详细信息")


class ShareReportResponse(BaseModel):
    """分享响应"""

    incident_id: str
    report_id: str
    share_token: str
    share_url: str
    created_at: datetime


@router.get(
    "/shared/{token}",
    response_model=ReportResponse,
    summary="通过分享链接获取报告",
    description="通过分享 token 获取报告",
)
async def get_shared_report(token: str):
    report = await report_service.get_report_by_share_token(token)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared report not found",
        )
    return _build_report_response(report)


@router.get(
    "/{incident_id}",
    response_model=ReportResponse,
    summary="获取分析报告",
    description="获取指定故障事件的分析报告（不存在则自动生成）",
)
async def get_report(incident_id: str):
    try:
        report = await report_service.get_report(incident_id)
        if not report:
            report = await report_service.get_or_generate_report(
                incident_id=incident_id,
                format="markdown",
            )
        return _build_report_response(report)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/{incident_id}/export",
    response_model=ReportResponse,
    summary="导出报告",
    description="导出分析报告为指定格式",
)
async def export_report(incident_id: str, request: ReportExportRequest):
    if request.format == "pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF export is not implemented yet",
        )

    try:
        report = await report_service.get_or_generate_report(
            incident_id=incident_id,
            format=request.format,
            force_regenerate=False,
        )
        return _build_report_response(report)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/{incident_id}/regenerate",
    response_model=ReportResponse,
    summary="重新生成报告",
    description="重新生成分析报告",
)
async def regenerate_report(incident_id: str):
    try:
        report = await report_service.regenerate_report(
            incident_id=incident_id,
            format="markdown",
        )
        return _build_report_response(report)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get(
    "/{incident_id}/share",
    response_model=ShareReportResponse,
    summary="分享报告",
    description="生成报告分享链接",
)
async def share_report(incident_id: str):
    try:
        share = await report_service.create_share_link(incident_id)
        return ShareReportResponse(**share)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


def _build_report_response(report: dict) -> ReportResponse:
    return ReportResponse(
        report_id=report["report_id"],
        incident_id=report["incident_id"],
        debate_session_id=report.get("debate_session_id"),
        format=report["format"],
        content=report["content"],
        file_path=report.get("file_path"),
        generated_at=report["generated_at"],
    )

