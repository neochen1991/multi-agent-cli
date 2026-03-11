"""test治理人工审核相关测试。"""

import asyncio

from app.services.governance_ops_service import GovernanceOpsService


def test_list_human_reviews_filters_pending_and_approved(tmp_path, monkeypatch):
    """验证list人工reviewsfilterspendingandapproved。"""
    
    service = GovernanceOpsService()
    monkeypatch.setattr(service, "_debates_file", tmp_path / "debates.json")
    service._write_json(
        service._debates_file,
        {
            "sessions": [
                {
                    "id": "deb_pending",
                    "incident_id": "inc_1",
                    "status": "waiting",
                    "updated_at": "2026-03-07T10:00:00",
                    "context": {
                        "execution_mode": "standard",
                        "deployment_profile": {"name": "production_governed"},
                        "human_review": {
                            "status": "pending",
                            "reason": "需要人工确认",
                            "resume_from_step": "report_generation",
                            "requested_at": "2026-03-07T09:00:00",
                        },
                        "pending_review_checkpoint": {
                            "debate_result": {"root_cause": "db lock", "confidence": 0.81},
                        },
                    },
                },
                {
                    "id": "deb_approved",
                    "incident_id": "inc_2",
                    "status": "waiting",
                    "updated_at": "2026-03-07T11:00:00",
                    "context": {
                        "execution_mode": "background",
                        "deployment_profile": {"name": "production_governed"},
                        "human_review": {
                            "status": "approved",
                            "reason": "已人工确认",
                            "resume_from_step": "report_generation",
                            "requested_at": "2026-03-07T08:00:00",
                            "approver": "alice",
                        },
                        "pending_review_checkpoint": {
                            "debate_result": {"root_cause": "cache stampede", "confidence": 0.72},
                        },
                    },
                },
                {
                    "id": "deb_completed",
                    "incident_id": "inc_3",
                    "status": "completed",
                    "updated_at": "2026-03-07T12:00:00",
                    "context": {
                        "human_review": {"status": "completed"},
                    },
                },
            ],
            "results": [],
        },
    )

    rows = service._read_json(service._debates_file, {})
    assert len(rows["sessions"]) == 3

    items = asyncio.run(service.list_human_reviews(limit=10))

    assert [item["session_id"] for item in items] == ["deb_pending", "deb_approved"]
    assert items[0]["review_status"] == "pending"
    assert items[0]["root_cause"] == "db lock"
    assert items[1]["review_status"] == "approved"
    assert items[1]["approver"] == "alice"


def test_team_metrics_breaks_out_queue_timeout_hotspots(tmp_path, monkeypatch):
    """验证teammetricsbreaksout队列超时hotspots。"""
    
    service = GovernanceOpsService()
    monkeypatch.setattr(service, "_debates_file", tmp_path / "debates.json")
    monkeypatch.setattr(service, "_runtime_events_dir", tmp_path / "runtime_events")
    service._runtime_events_dir.mkdir(parents=True, exist_ok=True)

    service._write_json(
        service._debates_file,
        {
            "sessions": [
                {
                    "id": "deb_queue",
                    "incident_id": "inc_queue",
                    "status": "completed",
                    "tenant_id": "order-sre",
                    "created_at": "2026-03-07T10:00:00+00:00",
                    "context": {},
                }
            ],
            "results": [
                {
                    "session_id": "deb_queue",
                    "confidence": 0.42,
                    "risk_assessment": {"risk_factors": ["关键证据不足：成功=1，降级=3，缺失=0"]},
                }
            ],
        },
    )

    (service._runtime_events_dir / "deb_queue.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-03-07T10:00:00+00:00","type":"llm_http_request","agent_name":"LogAgent","prompt_length":800,"max_tokens":300}',
                '{"timestamp":"2026-03-07T10:00:03+00:00","type":"llm_queue_timeout","agent_name":"ProblemAnalysisAgent"}',
                '{"timestamp":"2026-03-07T10:00:03+00:00","type":"agent_command_feedback","agent_name":"DatabaseAgent","evidence_status":"inferred_without_tool"}',
                '{"timestamp":"2026-03-07T10:00:04+00:00","type":"llm_call_timeout","agent_name":"LogAgent"}',
            ]
        ),
        encoding="utf-8",
    )

    payload = asyncio.run(service.team_metrics(days=30, limit=10))
    item = payload["items"][0]

    assert item["queue_timeouts"] == 1
    assert item["queue_timeout_rate"] == 1.0
    assert item["limited_analyses"] == 1
    assert item["limited_analysis_rate"] == 1.0
    assert item["evidence_gap_sessions"] == 1
    assert item["evidence_gap_rate"] == 1.0
    assert payload["queue_timeout_hotspots"][0]["key"] == "ProblemAnalysisAgent::llm_queue_timeout"
    assert payload["limited_analysis_hotspots"][0]["key"] == "DatabaseAgent::inferred_without_tool"


def test_team_metrics_tracks_depth_mode_and_multistep_investigation(tmp_path, monkeypatch):
    """治理指标应输出分析深度分布和多步调查命中率。"""

    service = GovernanceOpsService()
    monkeypatch.setattr(service, "_debates_file", tmp_path / "debates.json")
    monkeypatch.setattr(service, "_runtime_events_dir", tmp_path / "runtime_events")
    service._runtime_events_dir.mkdir(parents=True, exist_ok=True)

    service._write_json(
        service._debates_file,
        {
            "sessions": [
                {
                    "id": "deb_deep",
                    "incident_id": "inc_deep",
                    "status": "completed",
                    "tenant_id": "order-sre",
                    "created_at": "2026-03-07T10:00:00+00:00",
                    "context": {"analysis_depth_mode": "deep"},
                },
                {
                    "id": "deb_standard",
                    "incident_id": "inc_standard",
                    "status": "completed",
                    "tenant_id": "order-sre",
                    "created_at": "2026-03-07T11:00:00+00:00",
                    "context": {"analysis_depth_mode": "standard"},
                },
            ],
            "results": [
                {"session_id": "deb_deep", "confidence": 0.81},
                {"session_id": "deb_standard", "confidence": 0.72},
            ],
        },
    )

    (service._runtime_events_dir / "deb_deep.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-03-07T10:00:00+00:00","type":"llm_http_request","agent_name":"CodeAgent","prompt_length":800,"max_tokens":300}',
                '{"timestamp":"2026-03-07T10:00:02+00:00","type":"expert_investigation_started","agent_name":"CodeAgent","analysis_depth_mode":"deep"}',
                '{"timestamp":"2026-03-07T10:00:03+00:00","type":"expert_investigation_step_completed","agent_name":"CodeAgent","stage":"plan"}',
                '{"timestamp":"2026-03-07T10:00:04+00:00","type":"expert_investigation_completed","agent_name":"CodeAgent","analysis_depth_mode":"deep"}',
            ]
        ),
        encoding="utf-8",
    )
    (service._runtime_events_dir / "deb_standard.jsonl").write_text(
        "\n".join(
            [
                '{"timestamp":"2026-03-07T11:00:00+00:00","type":"llm_http_request","agent_name":"LogAgent","prompt_length":500,"max_tokens":200}'
            ]
        ),
        encoding="utf-8",
    )

    payload = asyncio.run(service.team_metrics(days=30, limit=10))
    item = payload["items"][0]

    assert item["depth_mode_distribution"]["deep"] == 1
    assert item["depth_mode_distribution"]["standard"] == 1
    assert item["expert_investigation_sessions"] == 1
    assert item["expert_investigation_rate"] == 0.5
    assert item["expert_investigation_steps"] == 1
