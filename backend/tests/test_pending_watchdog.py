"""Watchdog tests for stale running tasks."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.runtime.task_registry import RuntimeTaskRegistry


@pytest.mark.asyncio
async def test_runtime_task_watchdog_marks_stale_running_failed(tmp_path):
    registry = RuntimeTaskRegistry(base_dir=str(tmp_path))
    await registry.mark_started("deb_test_watchdog", task_type="debate", trace_id="trc_x")

    # Simulate stale heartbeat.
    stale = datetime.utcnow() - timedelta(seconds=600)
    registry._tasks["deb_test_watchdog"].updated_at = stale.isoformat()  # noqa: SLF001 - test watchdog behavior

    changed = await registry.sweep_stale_running(max_idle_seconds=30)
    assert changed == 1

    record = await registry.get("deb_test_watchdog")
    assert record is not None
    assert record.status == "failed"
    assert record.error == "runtime_task_watchdog_timeout"

