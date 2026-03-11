"""test运行时策略center相关测试。"""

from app.runtime.langgraph.strategy_center import RuntimeStrategyCenter


def test_strategy_center_selects_low_cost_for_quick_mode(tmp_path, monkeypatch):
    """验证 quick 模式仍会选择低成本运行时策略。"""

    center = RuntimeStrategyCenter()
    monkeypatch.setattr(center, "_file", tmp_path / "runtime_strategy.json")
    selected = center.select(severity="warning", execution_mode="quick")
    assert selected["name"] == "low_cost"
    assert selected["phase_mode"] == "economy"


def test_strategy_center_keeps_background_aligned_with_balanced(tmp_path, monkeypatch):
    """验证 background 只表示执行方式，不再触发高并发特化策略。"""

    center = RuntimeStrategyCenter()
    monkeypatch.setattr(center, "_file", tmp_path / "runtime_strategy.json")
    selected = center.select(severity="warning", execution_mode="background")
    assert selected["name"] == "balanced"
    assert selected["phase_mode"] == "standard"
