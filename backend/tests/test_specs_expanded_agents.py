"""test规格扩展Agent相关测试。"""

from app.runtime.langgraph.specs import agent_sequence


def test_agent_sequence_contains_new_analysis_agents():
    """验证Agentsequence包含新增分析Agent。"""
    
    specs = agent_sequence(enable_critique=True)
    names = [spec.name for spec in specs]
    assert "MetricsAgent" in names
    assert "ChangeAgent" in names
    assert "RunbookAgent" in names
    assert "VerificationAgent" in names


def test_verification_agent_after_judge():
    """验证verificationAgent后裁决。"""
    
    specs = agent_sequence(enable_critique=True)
    names = [spec.name for spec in specs]
    assert names.index("JudgeAgent") < names.index("VerificationAgent")
