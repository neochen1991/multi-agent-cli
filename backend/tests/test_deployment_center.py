"""test部署center相关测试。"""

from app.runtime.langgraph.deployment_center import DeploymentCenter


def test_deployment_center_defaults_to_skill_enabled(tmp_path, monkeypatch):
    """验证部署centerdefaultstoSkillenabled。"""
    
    center = DeploymentCenter()
    monkeypatch.setattr(center, "_file", tmp_path / "deployment_profile.json")
    active = center.get_active()
    assert active["active_profile"] == "skill_enabled"


def test_deployment_center_selects_baseline_for_quick_mode(tmp_path, monkeypatch):
    """验证部署centerselectsbaselineforquick模式。"""
    
    center = DeploymentCenter()
    monkeypatch.setattr(center, "_file", tmp_path / "deployment_profile.json")
    selected = center.select(severity="warning", execution_mode="quick")
    assert selected["name"] == "baseline"
    assert selected["collaboration_enabled"] is False
    assert selected["max_parallel_agents"] == 3
    assert "RunbookAgent" in selected["allowed_agents"]


def test_deployment_center_selects_governed_for_critical(tmp_path, monkeypatch):
    """验证部署centerselectsgovernedforcritical。"""
    
    center = DeploymentCenter()
    monkeypatch.setattr(center, "_file", tmp_path / "deployment_profile.json")
    selected = center.select(severity="critical", execution_mode="standard")
    assert selected["name"] == "production_governed"
    assert selected["governance_mode"] == "approval_ready"


def test_deployment_center_keeps_background_aligned_with_standard(tmp_path, monkeypatch):
    """验证 background 只表示执行方式，不再单独切换部署拓扑。"""

    center = DeploymentCenter()
    monkeypatch.setattr(center, "_file", tmp_path / "deployment_profile.json")
    selected = center.select(severity="warning", execution_mode="background")
    assert selected["name"] == "skill_enabled"
    assert selected["require_verification_plan"] is True
    assert selected["max_parallel_agents"] == 5


def test_deployment_center_keeps_same_allowed_agents_for_quick_and_standard(tmp_path, monkeypatch):
    """验证 quick/standard 的部署档只在预算上差异，不切换专家可选空间。"""

    center = DeploymentCenter()
    monkeypatch.setattr(center, "_file", tmp_path / "deployment_profile.json")
    quick = center.select(severity="warning", execution_mode="quick")
    standard = center.select(severity="warning", execution_mode="standard")

    assert quick["allowed_agents"] == standard["allowed_agents"]
    assert quick["max_parallel_agents"] < standard["max_parallel_agents"]
