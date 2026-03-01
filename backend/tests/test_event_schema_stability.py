from app.core.event_schema import enrich_event


def test_event_id_is_stable_for_same_payload_without_event_id():
    base = {
        "type": "agent_round",
        "timestamp": "2026-03-01T08:00:00.000000",
        "session_id": "deb_xxx",
        "trace_id": "trc_xxx",
        "phase": "analysis",
        "agent_name": "LogAgent",
        "round_number": 2,
        "loop_round": 1,
        "event_sequence": 5,
    }
    p1 = enrich_event(dict(base))
    p2 = enrich_event(dict(base))
    assert p1["event_id"] == p2["event_id"]


def test_event_id_keeps_explicit_value_when_provided():
    payload = enrich_event(
        {
            "type": "x",
            "timestamp": "2026-03-01T08:00:00.000000",
            "event_id": "evt_custom",
        }
    )
    assert payload["event_id"] == "evt_custom"
