from app.runtime.langgraph.services.routing_service import RoutingService


def test_route_after_analysis_parallel_respects_collaboration_flag():
    service = RoutingService()
    assert service.route_after_analysis_parallel(enable_collaboration=True) == "analysis_collaboration"
    assert service.route_after_analysis_parallel(enable_collaboration=False) == "critic"


def test_route_after_round_evaluate_uses_continue_flag():
    service = RoutingService()
    assert service.route_after_round_evaluate({"continue_next_round": True}) == "round_start"
    assert service.route_after_round_evaluate({"continue_next_round": False}) == "finalize"


def test_round_discussion_budget_clamps_bounds():
    service = RoutingService()
    assert service.round_discussion_budget(
        base_steps=2,
        enable_collaboration=False,
        enable_critique=False,
    ) >= 4
    assert service.round_discussion_budget(
        base_steps=60,
        enable_collaboration=True,
        enable_critique=True,
    ) <= 24
