import asyncio
from datetime import datetime
import os
import sys
import importlib

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.main import app
from app.models.debate import DebateResult, EvidenceItem
from app.repositories.debate_repository import InMemoryDebateRepository
from app.repositories.incident_repository import InMemoryIncidentRepository
from app.repositories.report_repository import InMemoryReportRepository
from app.repositories.asset_repository import InMemoryAssetRepository
from app.services.asset_service import asset_service
from app.services.asset_collection_service import asset_collection_service
from app.services.debate_service import debate_service
from app.services.incident_service import incident_service
from app.services.report_service import report_service
from app.config import settings

report_service_module = importlib.import_module("app.services.report_service")


def _reset_state() -> None:
    incident_service._repository = InMemoryIncidentRepository()
    debate_service._repository = InMemoryDebateRepository()
    report_service._repository = InMemoryReportRepository()
    asset_service._repository = InMemoryAssetRepository()


def _create_fake_report_generator():
    async def _fake_generate_report(
        incident,
        debate_result,
        assets,
        format="markdown",
        event_callback=None,
    ):
        _ = event_callback
        return {
            "report_id": "rpt_test_001",
            "incident_id": incident["id"],
            "format": format,
            "content": f"# fake report for {incident['id']}",
            "file_path": f"/tmp/fake_{incident['id']}.{format}",
            "generated_at": datetime.utcnow().isoformat(),
        }

    return _fake_generate_report


def test_create_debate_session_updates_incident_without_type_error():
    _reset_state()
    client = TestClient(app)

    created = client.post("/api/v1/incidents/", json={"title": "P0 incident"})
    assert created.status_code == 201
    incident_id = created.json()["id"]

    session_resp = client.post(f"/api/v1/debates/?incident_id={incident_id}")
    assert session_resp.status_code == 201
    assert session_resp.json()["incident_id"] == incident_id

    detail_resp = client.get(f"/api/v1/incidents/{incident_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "analyzing"
    assert detail_resp.json()["debate_session_id"] == session_resp.json()["id"]


def test_create_debate_session_supports_configurable_max_rounds():
    _reset_state()
    client = TestClient(app)

    created = client.post("/api/v1/incidents/", json={"title": "configurable rounds"})
    assert created.status_code == 201
    incident_id = created.json()["id"]

    session_resp = client.post(f"/api/v1/debates/?incident_id={incident_id}&max_rounds=4")
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    detail_resp = client.get(f"/api/v1/debates/{session_id}")
    assert detail_resp.status_code == 200
    debate_config = (detail_resp.json().get("context") or {}).get("debate_config") or {}
    assert debate_config.get("max_rounds") == 4


def test_report_endpoints_work_with_in_memory_storage(monkeypatch):
    _reset_state()
    client = TestClient(app)

    # 避免真实 LLM 调用，使用本地假实现
    monkeypatch.setattr(
        report_service_module.report_generation_service,
        "generate_report",
        _create_fake_report_generator(),
    )

    created = client.post("/api/v1/incidents/", json={"title": "report incident"})
    assert created.status_code == 201
    incident = created.json()
    incident_id = incident["id"]

    session_resp = client.post(f"/api/v1/debates/?incident_id={incident_id}")
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    # 注入最小辩论结果，供报告生成使用
    result = DebateResult(
        session_id=session_id,
        incident_id=incident_id,
        root_cause="Null pointer in create order",
        root_cause_category="runtime",
        confidence=0.91,
        evidence_chain=[
            EvidenceItem(
                type="log",
                description="gateway 502 timeout after 30s",
                source="log",
                location=None,
                strength="strong",
            ),
            EvidenceItem(
                type="code",
                description="OrderAppService transaction too long",
                source="code",
                location=None,
                strength="medium",
            ),
        ],
    )
    asyncio.run(debate_service._repository.save_result(result))

    regen = client.post(f"/api/v1/reports/{incident_id}/regenerate")
    assert regen.status_code == 200
    assert regen.json()["incident_id"] == incident_id

    latest = client.get(f"/api/v1/reports/{incident_id}")
    assert latest.status_code == 200
    assert latest.json()["report_id"] == "rpt_test_001"

    export_resp = client.post(
        f"/api/v1/reports/{incident_id}/export",
        json={"format": "json", "include_details": True},
    )
    assert export_resp.status_code == 200
    assert export_resp.json()["format"] == "json"

    share = client.get(f"/api/v1/reports/{incident_id}/share")
    assert share.status_code == 200
    token = share.json()["share_token"]

    shared = client.get(f"/api/v1/reports/shared/{token}")
    assert shared.status_code == 200
    assert shared.json()["incident_id"] == incident_id


def test_asset_repository_backed_endpoints_work():
    _reset_state()
    client = TestClient(app)

    runtime = client.post(
        "/api/v1/assets/runtime/",
        json={"type": "log", "source": "app.log", "raw_content": "NullPointerException"},
    )
    assert runtime.status_code == 201
    runtime_id = runtime.json()["id"]

    dev = client.post(
        "/api/v1/assets/dev/",
        json={
            "type": "code",
            "name": "OrderService.java",
            "path": "src/OrderService.java",
            "language": "java",
            "content": "class OrderService {}",
        },
    )
    assert dev.status_code == 201
    dev_id = dev.json()["id"]

    design = client.post(
        "/api/v1/assets/design/",
        json={"type": "ddd_document", "name": "Order Domain", "domain": "order"},
    )
    assert design.status_code == 201
    design_id = design.json()["id"]

    linked = client.post(
        "/api/v1/assets/link",
        params={
            "runtime_asset_id": runtime_id,
            "dev_asset_id": dev_id,
            "design_asset_id": design_id,
        },
    )
    assert linked.status_code == 200

    dev_search = client.get("/api/v1/assets/dev/search", params={"q": "OrderService"})
    assert dev_search.status_code == 200
    assert dev_search.json()["total"] == 1


def test_asset_fusion_endpoint_returns_session_assets():
    _reset_state()
    client = TestClient(app)

    created = client.post("/api/v1/incidents/", json={"title": "fusion incident"})
    assert created.status_code == 201
    incident_id = created.json()["id"]

    session_resp = client.post(f"/api/v1/debates/?incident_id={incident_id}")
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    # 手动注入 assets 到 session context，模拟采集结果
    session = asyncio.run(debate_service.get_session(session_id))
    assert session is not None
    session.context["assets"] = {
        "runtime_assets": [{"id": "rt_1", "service_name": "order-service", "parsed_data": {"key_classes": ["OrderService"]}}],
        "dev_assets": [{"id": "dev_1", "name": "OrderService.java", "parsed_data": {"class_name": "OrderService"}}],
        "design_assets": [{"id": "des_1", "domain": "order"}],
    }
    asyncio.run(debate_service._repository.save_session(session))

    fusion = client.get(f"/api/v1/assets/fusion/{incident_id}")
    assert fusion.status_code == 200
    payload = fusion.json()
    assert payload["incident_id"] == incident_id
    assert len(payload["relationships"]) >= 1


def test_auth_login_and_guard_when_enabled():
    _reset_state()
    client = TestClient(app)
    previous = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        unauthorized = client.get("/api/v1/incidents/")
        assert unauthorized.status_code == 401

        login = client.post("/api/v1/auth/login", json={"username": "analyst", "password": "analyst123"})
        assert login.status_code == 200
        token = login.json()["access_token"]
        assert token

        authorized = client.get("/api/v1/incidents/", headers={"Authorization": f"Bearer {token}"})
        assert authorized.status_code == 200
    finally:
        settings.AUTH_ENABLED = previous


def test_collect_assets_tolerates_none_metadata_and_parsed_data(monkeypatch):
    _reset_state()

    async def _fake_runtime_assets(*args, **kwargs):
        return []

    async def _fake_dev_assets(*args, **kwargs):
        return []

    async def _fake_design_assets(*args, **kwargs):
        return []

    monkeypatch.setattr(asset_collection_service, "collect_runtime_assets", _fake_runtime_assets)
    monkeypatch.setattr(asset_collection_service, "collect_dev_assets", _fake_dev_assets)
    monkeypatch.setattr(asset_collection_service, "collect_design_assets", _fake_design_assets)

    assets = asyncio.run(
        debate_service._collect_assets(
            {
                "incident": {"id": "inc_test_01", "metadata": None},
                "log_content": "error log",
                "parsed_data": None,
            }
        )
    )

    assert assets["runtime_assets"] == []
    assert assets["dev_assets"] == []
    assert assets["design_assets"] == []


def test_execute_debate_degrades_when_llm_unavailable(monkeypatch):
    _reset_state()
    client = TestClient(app)
    monkeypatch.setattr(settings, "DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION", False)

    monkeypatch.setattr(
        report_service_module.report_generation_service,
        "generate_report",
        _create_fake_report_generator(),
    )

    async def _always_fail_ai_debate(*args, **kwargs):
        raise RuntimeError("LLM_RATE_LIMITED: mock 429")

    monkeypatch.setattr(debate_service, "_execute_ai_debate", _always_fail_ai_debate)

    created = client.post("/api/v1/incidents/", json={"title": "llm unavailable incident"})
    assert created.status_code == 201
    incident_id = created.json()["id"]

    session_resp = client.post(f"/api/v1/debates/?incident_id={incident_id}")
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    execute_resp = client.post(f"/api/v1/debates/{session_id}/execute")
    assert execute_resp.status_code == 200
    payload = execute_resp.json()
    assert payload["session_id"] == session_id
    assert "LLM 服务繁忙" in payload["root_cause"]
    assert payload["confidence"] > 0

    latest = client.get(f"/api/v1/debates/{session_id}/result")
    assert latest.status_code == 200


def test_execute_debate_accepts_coordination_phase_in_history(monkeypatch):
    _reset_state()
    client = TestClient(app)
    monkeypatch.setattr(settings, "DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION", False)
    monkeypatch.setattr(
        report_service_module.report_generation_service,
        "generate_report",
        _create_fake_report_generator(),
    )

    async def _fake_ai_debate(*args, **kwargs):
        return (
            {
                "confidence": 0.84,
                "consensus_reached": True,
                "executed_rounds": 1,
                "final_judgment": {
                    "root_cause": {
                        "summary": "连接池泄漏导致订单接口线程耗尽",
                        "category": "resource_exhaustion",
                        "confidence": 0.84,
                    },
                    "evidence_chain": [],
                },
                "debate_history": [
                    {
                        "round_number": 1,
                        "phase": "coordination",
                        "agent_name": "ProblemAnalysisAgent",
                        "agent_role": "问题分析主Agent/调度协调者",
                        "model": {"name": "kimi-k2.5"},
                        "input_message": "启动分析",
                        "output_content": {
                            "analysis": "分派任务给日志/代码/领域专家",
                            "conclusion": "先进行并行分析",
                            "confidence": 0.62,
                        },
                        "confidence": 0.62,
                    },
                    {
                        "round_number": 2,
                        "phase": "judgment",
                        "agent_name": "JudgeAgent",
                        "agent_role": "技术委员会主席",
                        "model": {"name": "kimi-k2.5"},
                        "input_message": "汇总结论",
                        "output_content": {
                            "conclusion": "连接池泄漏导致订单接口线程耗尽",
                            "confidence": 0.84,
                        },
                        "confidence": 0.84,
                    },
                ],
            },
            "ags_test_coord",
        )

    monkeypatch.setattr(debate_service, "_execute_ai_debate", _fake_ai_debate)

    created = client.post("/api/v1/incidents/", json={"title": "coordination phase incident"})
    assert created.status_code == 201
    incident_id = created.json()["id"]

    session_resp = client.post(f"/api/v1/debates/?incident_id={incident_id}")
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    execute_resp = client.post(f"/api/v1/debates/{session_id}/execute")
    assert execute_resp.status_code == 200
    payload = execute_resp.json()
    assert payload["session_id"] == session_id
    assert "连接池泄漏" in payload["root_cause"]

    detail_resp = client.get(f"/api/v1/debates/{session_id}")
    assert detail_resp.status_code == 200
    rounds = detail_resp.json().get("rounds") or []
    assert rounds
    # coordination phase is now a first-class persisted phase.
    assert rounds[0]["phase"] == "coordination"


def test_interface_locate_endpoint_maps_to_domain_aggregate():
    _reset_state()
    client = TestClient(app)

    payload = {
        "log_content": (
            "2026-02-18 10:00:00 ERROR POST /api/v1/orders failed with "
            "java.lang.NullPointerException at OrderAppService#createOrder"
        ),
        "symptom": "用户反馈下单失败，返回500",
    }

    resp = client.post("/api/v1/assets/locate", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["matched"] is True
    assert data["domain"] == "order"
    assert data["aggregate"] == "OrderAggregate"
    assert len(data["code_artifacts"]) > 0
    assert "t_order" in data["db_tables"]
