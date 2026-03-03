"""Fixture loading for RCA benchmark runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class IncidentFixture:
    fixture_id: str
    title: str
    symptom: str
    log_excerpt: str
    stacktrace: str
    expected_root_cause: str
    expected_domain: str
    expected_aggregate: str


def _fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "incidents"


def load_fixtures(limit: int = 0) -> List[IncidentFixture]:
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
                symptom=str(payload.get("symptom") or ""),
                log_excerpt=str(payload.get("log_excerpt") or ""),
                stacktrace=str(payload.get("stacktrace") or ""),
                expected_root_cause=str(payload.get("expected_root_cause") or ""),
                expected_domain=str(payload.get("expected_domain") or ""),
                expected_aggregate=str(payload.get("expected_aggregate") or ""),
            )
        )
    return fixtures

