from app.services.debate_service import DebateService


def test_classify_error_prefers_rate_limit_over_no_effective_conclusion():
    error_text = (
        "未获得有效大模型结论: ProblemAnalysisAgent 调用不可恢复失败: "
        "LLM_RATE_LIMITED: Error code: 429 - {'error': {'code': 'AccountQuotaExceeded', "
        "'message': 'You have exceeded the 5-hour usage quota. It will reset at 2026-03-09 22:55:57 +0800 CST.'}}"
    )

    payload = DebateService._classify_error(error_text)  # noqa: SLF001

    assert payload["error_code"] == "LLM_RATE_LIMITED"
    assert payload["recoverable"] is True
    assert "2026-03-09 22:55:57 +0800 CST" in payload["retry_hint"]


def test_classify_error_preserves_no_effective_conclusion_when_no_rate_limit():
    error_text = "未获得有效大模型结论: 证据冲突，无法收敛"

    payload = DebateService._classify_error(error_text)  # noqa: SLF001

    assert payload["error_code"] == "NO_EFFECTIVE_LLM_CONCLUSION"
    assert payload["recoverable"] is True
