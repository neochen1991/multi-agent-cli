from app.runtime.judgement.topology_reasoner import score_topology_propagation


def test_topology_reasoner_scores_and_paths():
    context = {
        "assets": {
            "interface_mapping": {
                "domain": "order",
                "aggregate": "order",
                "owner_team": "order-domain-team",
                "matched_endpoint": {"service": "order-service", "path": "/api/v1/orders"},
            }
        }
    }
    evidence = [
        {
            "source": "runtime_log",
            "description": "gateway timeout /api/v1/orders",
            "source_ref": "trace:trc_1",
        },
        {
            "source": "code_repo",
            "description": "order-service transaction blocked",
            "source_ref": "OrderAppService.java:147",
        },
    ]
    result = score_topology_propagation(context=context, evidence=evidence)
    assert result["topology_score"] > 0
    assert result["propagation_hits"] >= 1
    assert isinstance(result["propagation_paths"], list)
