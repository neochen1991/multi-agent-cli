"""Benchmark harness runner for incident fixtures."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List

import structlog

from app.benchmark.fixtures import IncidentFixture, load_fixtures
from app.benchmark.scoring import aggregate_cases, evaluate_case
from app.models.incident import IncidentCreate, IncidentSource, IncidentStatus, IncidentUpdate
from app.services.debate_service import debate_service
from app.services.incident_service import incident_service

logger = structlog.get_logger()


@dataclass(frozen=True)
class BenchmarkRunOptions:
    limit: int = 3
    timeout_seconds: int = 240
    write_baseline: bool = True


class BenchmarkRunner:
    """Execute fixtures end-to-end and produce a baseline report JSON."""

    def __init__(self) -> None:
        self._metrics_dir = Path(__file__).resolve().parents[3] / "docs" / "metrics"
        self._metrics_dir.mkdir(parents=True, exist_ok=True)

    async def _cleanup_stale_benchmark_incidents(self) -> int:
        """Backfill old benchmark incidents that remained pending in previous versions."""
        listing = await incident_service.list_incidents(page=1, page_size=500)
        updated = 0
        for incident in listing.items:
            title = str(incident.title or "")
            if not title.startswith("[benchmark]"):
                continue
            if incident.status != IncidentStatus.PENDING:
                continue
            await incident_service.update_incident(
                incident.id,
                IncidentUpdate(
                    status=IncidentStatus.CLOSED,
                    fix_suggestion="benchmark pending backfilled",
                    debate_session_id=incident.debate_session_id,
                ),
            )
            updated += 1
        if updated:
            logger.info("benchmark_pending_backfilled", count=updated)
        return updated

    async def _run_one(self, fixture: IncidentFixture, timeout_seconds: int) -> Dict[str, Any]:
        started = perf_counter()
        status = "ok"
        predicted_root_cause = ""
        confidence = 0.0
        session_id = ""
        incident_id = ""
        error = ""
        try:
            incident = await incident_service.create_incident(
                IncidentCreate(
                    title=f"[benchmark] {fixture.title}",
                    description=fixture.symptom,
                    source=IncidentSource.MANUAL,
                    log_content=f"{fixture.log_excerpt}\n\n{fixture.symptom}",
                    exception_stack=fixture.stacktrace,
                    service_name="benchmark-service",
                    environment="benchmark",
                    metadata={"fixture_id": fixture.fixture_id},
                )
            )
            incident_id = incident.id
            session = await debate_service.create_session(incident, max_rounds=1)
            session_id = session.id
            await incident_service.update_incident(
                incident_id,
                IncidentUpdate(
                    status=IncidentStatus.ANALYZING,
                    debate_session_id=session_id,
                ),
            )
            result = await asyncio.wait_for(
                debate_service.execute_debate(session.id),
                timeout=max(30, int(timeout_seconds or 240)),
            )
            predicted_root_cause = str(result.root_cause or "")
            confidence = float(result.confidence or 0.0)
            await incident_service.update_incident(
                incident_id,
                IncidentUpdate(
                    status=IncidentStatus.RESOLVED,
                    root_cause=predicted_root_cause or None,
                    fix_suggestion=(result.fix_recommendation.summary if result.fix_recommendation else None),
                    debate_session_id=session_id,
                ),
            )
        except asyncio.TimeoutError:
            status = "timeout"
            error = "benchmark case timed out"
            if session_id:
                await debate_service.cancel_session(session_id, reason="benchmark_timeout")
            if incident_id:
                await incident_service.update_incident(
                    incident_id,
                    IncidentUpdate(
                        status=IncidentStatus.CLOSED,
                        debate_session_id=session_id or None,
                        fix_suggestion=error,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            status = f"error:{exc.__class__.__name__}"
            error = str(exc)
            if session_id:
                await debate_service.cancel_session(session_id, reason="benchmark_error")
            if incident_id:
                await incident_service.update_incident(
                    incident_id,
                    IncidentUpdate(
                        status=IncidentStatus.CLOSED,
                        debate_session_id=session_id or None,
                        fix_suggestion=error[:320],
                    ),
                )
        duration_ms = round((perf_counter() - started) * 1000, 2)
        score = evaluate_case(
            expected_root_cause=fixture.expected_root_cause,
            predicted_root_cause=predicted_root_cause,
            confidence=confidence,
            duration_ms=duration_ms,
            status=status,
        )
        return {
            "fixture_id": fixture.fixture_id,
            "incident_id": incident_id,
            "session_id": session_id,
            "expected_root_cause": fixture.expected_root_cause,
            "expected_domain": fixture.expected_domain,
            "expected_aggregate": fixture.expected_aggregate,
            "predicted_root_cause": predicted_root_cause,
            "status": status,
            "error": error,
            **score,
        }

    async def run(self, options: BenchmarkRunOptions | None = None) -> Dict[str, Any]:
        opts = options or BenchmarkRunOptions()
        await self._cleanup_stale_benchmark_incidents()
        fixtures = load_fixtures(limit=max(1, int(opts.limit or 3)))
        cases: List[Dict[str, Any]] = []
        for fixture in fixtures:
            row = await self._run_one(fixture, timeout_seconds=opts.timeout_seconds)
            cases.append(row)
            logger.info(
                "benchmark_case_completed",
                fixture_id=fixture.fixture_id,
                status=row.get("status"),
                overlap_score=row.get("overlap_score"),
                duration_ms=row.get("duration_ms"),
            )
        summary = aggregate_cases(cases)
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "fixtures": len(fixtures),
            "summary": summary,
            "cases": cases,
        }
        if opts.write_baseline:
            file_name = f"baseline-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
            path = self._metrics_dir / file_name
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["baseline_file"] = str(path)
        return report


benchmark_runner = BenchmarkRunner()
