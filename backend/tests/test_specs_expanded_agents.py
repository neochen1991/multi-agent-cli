from app.runtime.langgraph.specs import agent_sequence


def test_agent_sequence_contains_new_analysis_agents():
    specs = agent_sequence(enable_critique=True)
    names = [spec.name for spec in specs]
    assert "MetricsAgent" in names
    assert "ChangeAgent" in names
    assert "RunbookAgent" in names
    assert "VerificationAgent" in names


def test_verification_agent_after_judge():
    specs = agent_sequence(enable_critique=True)
    names = [spec.name for spec in specs]
    assert names.index("JudgeAgent") < names.index("VerificationAgent")
