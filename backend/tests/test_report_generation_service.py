"""ReportGenerationService 的 confidence 与时间统一测试。"""

from __future__ import annotations

from app.services.report_generation_service import ReportGenerationService


def test_report_generation_prefers_meaningful_root_cause_confidence() -> None:
    """报告侧应优先保留 Judge 根因的有效置信度。"""

    service = ReportGenerationService()
    debate_result = {
        "confidence": 0.45,
        "final_judgment": {
            "root_cause": {
                "summary": "网关路由表未同步 order-service 实例，导致网关层直接返回 404。",
                "category": "infrastructure.gateway-route-miss",
                "confidence": 0.68,
            },
            "evidence_chain": [
                {
                    "type": "log",
                    "description": "gateway route not found path=/api/v1/orders",
                    "source": "gateway",
                }
            ],
        },
    }

    assert service._effective_debate_confidence(debate_result) == 0.68


def test_report_generation_skip_reason_uses_effective_confidence() -> None:
    """当 Judge 已形成有效根因时，不应因为顶层旧 confidence 偏低而跳过报告 LLM。"""

    service = ReportGenerationService()
    debate_result = {
        "confidence": 0.22,
        "final_judgment": {
            "root_cause": {
                "summary": "支付确认链路缺少总超时预算，RiskService 三次重试耗尽主链路时间。",
                "category": "upstream_timeout_budget_missing",
                "confidence": 0.72,
            },
            "evidence_chain": [
                {"type": "log", "description": "三次 timeout + backoff 累积约 30.4s", "source": "LogAgent"},
                {"type": "code", "description": "PaymentAppService.confirm -> RiskClient.check", "source": "CodeAgent"},
            ],
        },
    }

    assert service._report_ai_skip_reason(debate_result) is None


def test_report_generation_json_uses_effective_confidence() -> None:
    """JSON 报告元数据应写入统一后的最终置信度。"""

    service = ReportGenerationService()
    report_content = service._get_default_report_structure()
    incident = {"id": "inc_test", "title": "test incident"}
    debate_result = {
        "confidence": 0.45,
        "final_judgment": {
            "root_cause": {
                "summary": "数据库锁等待只是放大器，主因是长事务。",
                "category": "transaction_scope_too_wide",
                "confidence": 0.73,
            },
            "evidence_chain": [{"type": "code", "description": "事务边界覆盖远程调用", "source": "CodeAgent"}],
        },
    }

    payload = service._format_as_json(report_content, incident, debate_result, assets={})

    assert '"confidence": 0.73' in payload
