"""Smoke 场景回归测试。"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path("/Users/neochen/multi-agent-cli_v2")
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "smoke-e2e.mjs"
PAYMENT_FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "incidents" / "inc_22.json"


def test_payment_smoke_uses_richer_fixture_file():
    """支付超时 smoke 应有 richer fixture，避免只靠单条摘要日志。"""

    assert PAYMENT_FIXTURE.exists()
    payload = json.loads(PAYMENT_FIXTURE.read_text())

    assert payload["scenario"] == "upstream-timeout-with-retry-budget-gap"
    assert "RiskService" in str(payload.get("log_excerpt") or "")
    assert "retries=3" in str(payload.get("log_excerpt") or "")
    assert "SocketTimeoutException" in str(payload.get("stacktrace") or "")
    assert len(list(payload.get("expected_causal_chain") or [])) >= 4


def test_smoke_script_forwards_optional_incident_context_fields():
    """smoke 创建 incident 时应把 richer fixture 的上下文一起传给后端。"""

    content = SMOKE_SCRIPT.read_text()

    assert "exception_stack: scenario.exception_stack" in content
    assert "trace_id: scenario.trace_id" in content
    assert "metadata: scenario.metadata" in content
