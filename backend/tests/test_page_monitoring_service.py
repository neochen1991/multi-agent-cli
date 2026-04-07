"""页面自动巡检服务测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.page_monitoring_service as monitor_module
from app.models.incident import Incident, IncidentSource, IncidentStatus
from app.models.monitoring import MonitorTargetCreate
from app.storage.sqlite_store import SqliteStore


@pytest.mark.asyncio
async def test_page_monitoring_service_target_crud(tmp_path, monkeypatch):
    """验证巡检目标的创建/更新/删除链路。"""

    monkeypatch.setattr(monitor_module, "sqlite_store", SqliteStore(str(tmp_path / "monitor.db")))
    service = monitor_module.PageMonitoringService()

    created = await service.create_target(
        MonitorTargetCreate(
            name="订单页",
            url="https://example.com/orders",
            check_interval_sec=30,
            timeout_sec=10,
            cooldown_sec=120,
            cookie_header="sessionid=abc123; token=xyz",
        )
    )
    assert created.name == "订单页"
    assert created.cookie_header == "sessionid=abc123; token=xyz"

    listed = await service.list_targets()
    assert len(listed) == 1
    assert listed[0].id == created.id

    updated = await service.update_target(created.id, monitor_module.MonitorTargetUpdate(enabled=False))
    assert updated is not None
    assert updated.enabled is False

    deleted = await service.delete_target(created.id)
    assert deleted is True
    assert await service.get_target(created.id) is None


@pytest.mark.asyncio
async def test_page_monitoring_service_scan_triggers_incident_pipeline(tmp_path, monkeypatch):
    """验证巡检命中异常后会自动创建 incident 并拉起 RCA 会话。"""

    monkeypatch.setattr(monitor_module, "sqlite_store", SqliteStore(str(tmp_path / "monitor-trigger.db")))

    incident_updates = []
    created_incidents = []

    async def _fake_create_incident(payload):
        incident = Incident(
            id="inc_auto_1",
            title=payload.title,
            description=payload.description,
            source=IncidentSource.MONITOR,
            status=IncidentStatus.PENDING,
            service_name=payload.service_name,
            metadata=payload.metadata or {},
        )
        created_incidents.append(incident)
        return incident

    async def _fake_update_incident(incident_id, payload):
        incident_updates.append((incident_id, payload))
        return None

    async def _fake_search_reference_entries(*, query, limit=5, entry_types=None):
        _ = query, limit, entry_types
        return [
            {"title": "网关 5xx 激增排查 SOP", "summary": "先看网关日志与上游耗时"},
            {"title": "连接池耗尽处置", "summary": "限流并缩短事务"},
        ]

    async def _fake_create_session(incident, max_rounds=None, analysis_depth_mode=None, execution_mode="quick"):
        _ = incident, max_rounds, analysis_depth_mode, execution_mode
        return SimpleNamespace(id="deb_auto_1")

    class _FakeTaskQueue:
        def submit(self, coro_factory, timeout_seconds=None):
            _ = coro_factory, timeout_seconds
            return "tsk_auto_1"

    monkeypatch.setattr(monitor_module.incident_service, "create_incident", _fake_create_incident)
    monkeypatch.setattr(monitor_module.incident_service, "update_incident", _fake_update_incident)
    monkeypatch.setattr(monitor_module.knowledge_service, "search_reference_entries", _fake_search_reference_entries)
    monkeypatch.setattr(monitor_module.debate_service, "create_session", _fake_create_session)
    monkeypatch.setattr(monitor_module, "task_queue", _FakeTaskQueue())

    service = monitor_module.PageMonitoringService()
    target = await service.create_target(
        MonitorTargetCreate(
            name="支付页",
            url="https://example.com/pay",
            check_interval_sec=30,
            timeout_sec=10,
            cooldown_sec=60,
            service_name="payment-web",
        )
    )

    async def _fake_scan_with_playwright(_target):
        return {
            "checker": "playwright",
            "has_error": True,
            "frontend_errors": ["console:error Uncaught TypeError"],
            "api_errors": ["500 POST https://api.example.com/orders"],
            "browser_error": "",
            "summary": "页面发现前端和接口异常",
        }

    monkeypatch.setattr(service, "_scan_with_playwright", _fake_scan_with_playwright)

    finding = await service.scan_target_once(target.id)
    assert finding is not None
    assert finding.has_error is True
    assert len(created_incidents) == 1
    assert created_incidents[0].metadata.get("monitor_target_id") == target.id
    assert incident_updates, "应至少有一次 incident 状态更新"


@pytest.mark.asyncio
async def test_page_monitoring_http_scan_passes_cookie_header(tmp_path, monkeypatch):
    """验证 HTTP 降级巡检会透传目标 Cookie。"""

    monkeypatch.setattr(monitor_module, "sqlite_store", SqliteStore(str(tmp_path / "monitor-http.db")))
    service = monitor_module.PageMonitoringService()
    target = await service.create_target(
        MonitorTargetCreate(
            name="需要登录页",
            url="https://example.com/private",
            cookie_header="sessionid=abc123; token=xyz",
        )
    )

    captured_headers = {}

    class _FakeResponse:
        status_code = 200

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            _ = exc_type, exc, tb
            return False

        async def get(self, url, headers=None):
            _ = url
            captured_headers.update(headers or {})
            return _FakeResponse()

    monkeypatch.setattr(monitor_module.httpx, "AsyncClient", _FakeClient)

    result = await service._scan_with_http(target)
    assert result["has_error"] is False
    assert captured_headers.get("Cookie") == "sessionid=abc123; token=xyz"


@pytest.mark.asyncio
async def test_query_api_candidate_detection_rules() -> None:
    """验证查询接口识别规则。"""

    service = monitor_module.PageMonitoringService()
    assert service._is_query_api_candidate(method="GET", url="https://api.example.com/orders?page=1") is True
    assert service._is_query_api_candidate(method="POST", url="https://api.example.com/search/orders") is True
    assert service._is_query_api_candidate(method="POST", url="https://api.example.com/order/query") is True
    assert service._is_query_api_candidate(method="POST", url="https://api.example.com/order/create") is False


@pytest.mark.asyncio
async def test_scan_target_summary_contains_query_and_replay_stats(tmp_path, monkeypatch):
    """验证巡检摘要会体现查询接口识别和回放异常统计。"""

    monkeypatch.setattr(monitor_module, "sqlite_store", SqliteStore(str(tmp_path / "monitor-summary.db")))
    service = monitor_module.PageMonitoringService()
    target = await service.create_target(
        MonitorTargetCreate(
            name="订单查询页",
            url="https://example.com/orders",
            check_interval_sec=30,
            timeout_sec=10,
            cooldown_sec=60,
        )
    )

    async def _fake_scan_with_playwright(_target):
        _ = _target
        return {
            "checker": "playwright",
            "has_error": True,
            "frontend_errors": ["console:error test"],
            "api_errors": ["500 GET https://api.example.com/orders/query"],
            "replay_api_errors": ["500 GET https://api.example.com/orders/query"],
            "observed_query_apis": [
                {"method": "GET", "url": "https://api.example.com/orders?status=*", "phase": "initial", "status": 200},
                {"method": "POST", "url": "https://api.example.com/orders/query", "phase": "replay", "status": 500},
            ],
            "triggered_actions": ["click:查询", "enter:input[type='search']"],
            "browser_error": "",
            "summary": "",
        }

    monkeypatch.setattr(service, "_scan_with_playwright", _fake_scan_with_playwright)
    finding = await service._scan_target(target)
    assert finding.has_error is True
    assert "回放异常1条" in finding.summary
    assert "接口异常1条" in finding.summary
    assert int(len((finding.raw or {}).get("observed_query_apis") or [])) == 2
