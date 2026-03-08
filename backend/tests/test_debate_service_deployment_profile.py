"""test辩论服务部署配置档相关测试。"""

import pytest

from app.models.incident import Incident, IncidentSeverity, IncidentStatus
from app.services.debate_service import DebateService


@pytest.mark.asyncio
async def test_create_session_persists_runtime_strategy_and_deployment_profile(monkeypatch):
    """验证创建session持久化运行时strategyand部署配置档。"""
    
    service = DebateService()

    async def _save_session(session):
        """为测试场景提供savesession辅助逻辑。"""
        return session

    monkeypatch.setattr(service._repository, "save_session", _save_session)

    incident = Incident(
        id="inc_deploy_profile",
        title="db timeout",
        description="db timeout",
        severity=IncidentSeverity.CRITICAL,
        status=IncidentStatus.PENDING,
        service_name="order-service",
    )

    session = await service.create_session(incident, max_rounds=1, execution_mode="standard")
    assert session.context["runtime_strategy"]["name"]
    assert session.context["deployment_profile"]["name"] == "production_governed"
    assert session.context["deployment_profile"]["collaboration_enabled"] is True


@pytest.mark.asyncio
async def test_execute_ai_debate_forwards_deployment_profile(monkeypatch):
    """验证执行辩论时会把部署配置透传给运行时。"""

    service = DebateService()
    captured: dict = {}

    class _FakeOrchestrator:
        """为测试场景提供假的辩论编排器。"""

        session_id = "deb_runtime_profile"

        async def execute(self, context, event_callback=None):  # noqa: ANN001
            """记录传入运行时的上下文并返回最小结果。"""
            _ = event_callback
            captured["context"] = context
            return {"confidence": 0.61, "final_judgment": {"root_cause": {"summary": "连接池耗尽"}}}

    monkeypatch.setattr(
        "app.services.debate_service.create_ai_debate_orchestrator",
        lambda **kwargs: _FakeOrchestrator(),
    )

    result, runtime_session_id = await service._execute_ai_debate(  # noqa: SLF001 - validating runtime context
        context={
            "incident": {
                "title": "订单提交大量 500",
                "description": "订单接口在高峰时段连接池耗尽",
                "severity": "critical",
                "service_name": "order-service",
            },
            "log_content": "db timeout",
            "trace_id": "trace-001",
            "execution_mode": "background",
            "runtime_strategy": {"phase_mode": "fast_track"},
            "deployment_profile": {"name": "investigation_full", "collaboration_enabled": True},
        },
        assets={
            "runtime_assets": [],
            "dev_assets": [],
            "design_assets": [],
            "interface_mapping": {},
            "investigation_leads": {},
        },
        event_callback=None,
        session_id="deb_runtime_profile",
    )

    assert result["final_judgment"]["root_cause"]["summary"] == "连接池耗尽"
    assert runtime_session_id == "deb_runtime_profile"
    assert captured["context"]["deployment_profile"]["name"] == "investigation_full"
    assert captured["context"]["deployment_profile"]["collaboration_enabled"] is True
    assert captured["context"]["incident"]["title"] == "订单提交大量 500"
    assert captured["context"]["title"] == "订单提交大量 500"
    assert captured["context"]["description"] == "订单接口在高峰时段连接池耗尽"
    assert captured["context"]["severity"] == "critical"
    assert captured["context"]["service_name"] == "order-service"
