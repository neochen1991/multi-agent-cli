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
