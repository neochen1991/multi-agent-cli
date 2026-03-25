"""Smoke 场景回归测试。"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path("/Users/neochen/multi-agent-cli_v2")
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "smoke-e2e.mjs"
PAYMENT_FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "incidents" / "inc_22.json"
IMPACT_FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "incidents" / "inc_23.json"


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


def test_impact_smoke_uses_fixture_with_expected_impact():
    """影响面 smoke 场景应携带 expected_impact，用于验证 richer impact 输出。"""

    assert IMPACT_FIXTURE.exists()
    payload = json.loads(IMPACT_FIXTURE.read_text())

    assert payload["scenario"] == "impact-scope-order-create-timeout"
    assert payload["expected_impact"]["affected_functions"] == ["订单创建"]
    assert "/api/v1/orders" in payload["expected_impact"]["affected_interfaces"]
    assert payload["expected_impact"]["require_user_scope"] is True


def test_smoke_script_validates_expected_impact_when_present():
    """smoke 脚本应在场景提供 expected_impact 时校验 richer impact 输出。"""

    content = SMOKE_SCRIPT.read_text()

    assert "function validateExpectedImpact(debateResult, scenario)" in content
    assert "completed_without_expected_impact" in content
    assert "impact_check_passed: impactCheck.ok" in content


def test_smoke_script_polls_artifacts_without_blocking_on_websocket_result():
    """WS 不返回最终 result 时，smoke 也应继续走 REST 轮询并及时退出。"""

    content = SMOKE_SCRIPT.read_text()

    assert "const artifactPromise = waitForDebateArtifacts(session.id, incident.id, token);" in content
    assert "const wsPromise = runRealtimeDebate(session.id, token);" in content
    assert "const artifacts = await artifactPromise;" in content


def test_smoke_script_prints_report_id_in_summary():
    """smoke 输出摘要时应包含 report_id，方便人工定位结果。"""

    content = SMOKE_SCRIPT.read_text()

    assert "report_id:" in content


def test_smoke_script_allows_completed_session_with_partial_artifact_snapshot():
    """会话已 completed 时，脚本应输出最后拿到的 detail/result/report，而不是一直卡到总超时。"""

    content = SMOKE_SCRIPT.read_text()

    assert "return {\n      detail: lastDetail,\n      debateResult: lastResult,\n      report: lastReport,\n      partial: true," in content
    assert "const effective = isEffectiveRootCause(debateResult?.root_cause);" in content
    assert "const reportGenerated = Boolean(report?.report_id);" in content
    assert "if (detail.status === 'completed' && !effective) {" in content
