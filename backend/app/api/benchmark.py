"""基线评测 API。

提供 benchmark 执行入口，以及历史基线结果文件的查询能力。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.benchmark.runner import BenchmarkRunOptions, benchmark_runner

router = APIRouter()


class BenchmarkRunResponse(BaseModel):
    """执行 benchmark 后返回的结果摘要。"""

    generated_at: str
    fixtures: int
    summary: Dict[str, Any]
    cases: List[Dict[str, Any]]
    baseline_file: Optional[str] = None


class BaselineFileResponse(BaseModel):
    """单个基线文件的元信息。"""

    file: str
    generated_at: str
    summary: Dict[str, Any] = Field(default_factory=dict)


def _metrics_dir() -> Path:
    """定位基线评测结果目录。"""
    return Path(__file__).resolve().parents[3] / "docs" / "metrics"


def _load_file(path: Path) -> Dict[str, Any]:
    """读取单个基线文件；解析失败时返回空字典，避免接口直接报错。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@router.post(
    "/run",
    response_model=BenchmarkRunResponse,
    summary="执行 benchmark 评测",
    description="对内置故障样本执行端到端分析并输出评分报告",
)
async def run_benchmark(
    limit: int = Query(3, ge=1, le=20, description="评测样本数"),
    timeout_seconds: int = Query(240, ge=30, le=1200, description="单样本超时时间"),
):
    """执行端到端基线评测并返回最新评分结果。"""
    report = await benchmark_runner.run(
        BenchmarkRunOptions(
            limit=int(limit),
            timeout_seconds=int(timeout_seconds),
            write_baseline=True,
        )
    )
    return BenchmarkRunResponse(**report)


@router.get(
    "/latest",
    response_model=Optional[BaselineFileResponse],
    summary="获取最近一次基线结果",
)
async def get_latest_baseline():
    """读取最近一次写入磁盘的 benchmark 基线文件。"""
    root = _metrics_dir()
    files = sorted(root.glob("baseline-*.json"), reverse=True)
    if not files:
        return None
    payload = _load_file(files[0])
    return BaselineFileResponse(
        file=str(files[0]),
        generated_at=str(payload.get("generated_at") or datetime.utcnow().isoformat()),
        summary=dict(payload.get("summary") or {}),
    )


@router.get(
    "/baselines",
    response_model=List[BaselineFileResponse],
    summary="列出基线结果文件",
)
async def list_baselines(limit: int = Query(20, ge=1, le=200)):
    """按时间倒序列出历史基线文件摘要。"""
    root = _metrics_dir()
    files = sorted(root.glob("baseline-*.json"), reverse=True)[: int(limit)]
    items: List[BaselineFileResponse] = []
    for path in files:
        payload = _load_file(path)
        items.append(
            BaselineFileResponse(
                file=str(path),
                generated_at=str(payload.get("generated_at") or ""),
                summary=dict(payload.get("summary") or {}),
            )
        )
    return items
