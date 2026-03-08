"""Fixture loading for RCA benchmark runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class IncidentFixture:
    """封装IncidentFixture相关数据结构或服务能力。"""
    fixture_id: str
    title: str
    scenario: str
    symptom: str
    log_excerpt: str
    stacktrace: str
    expected_root_cause: str
    expected_domain: str
    expected_aggregate: str
    owner: str
    tags: List[str]
    golden: bool


def _fixtures_dir() -> Path:
    """执行样例dir相关逻辑，并为当前模块提供可复用的处理能力。"""
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "incidents"


def load_fixtures(limit: int = 0) -> List[IncidentFixture]:
    """负责加载样例，并返回后续流程可直接消费的数据结果。"""
    root = _fixtures_dir()
    if not root.exists():
        return []
    files = sorted(p for p in root.glob("*.json") if p.is_file())
    if int(limit or 0) > 0:
        files = files[: int(limit)]
    fixtures: List[IncidentFixture] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        fixtures.append(
            IncidentFixture(
                fixture_id=str(payload.get("id") or path.stem),
                title=str(payload.get("title") or path.stem),
                scenario=str(payload.get("scenario") or payload.get("category") or path.stem),
                symptom=str(payload.get("symptom") or ""),
                log_excerpt=str(payload.get("log_excerpt") or ""),
                stacktrace=str(payload.get("stacktrace") or ""),
                expected_root_cause=str(payload.get("expected_root_cause") or ""),
                expected_domain=str(payload.get("expected_domain") or ""),
                expected_aggregate=str(payload.get("expected_aggregate") or ""),
                owner=str(payload.get("owner") or ""),
                tags=[
                    str(item).strip()
                    for item in list(payload.get("tags") or [])
                    if str(item).strip()
                ],
                golden=bool(payload.get("golden", False)),
            )
        )
    return fixtures
