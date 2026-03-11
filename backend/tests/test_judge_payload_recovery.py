"""test裁决载荷恢复相关测试。"""

from datetime import datetime

from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator, DebateTurn
from app.runtime.messages import AgentEvidence


def _orchestrator() -> LangGraphRuntimeOrchestrator:
    """为测试场景提供orchestrator辅助逻辑。"""
    
    return LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)


def test_judge_payload_recovery_from_truncated_response_keeps_root_cause():
    """验证裁决载荷恢复从truncatedresponse保留rootcause。"""
    
    orchestrator = _orchestrator()
    raw = """```json
{
  "final_judgment": {
    "root_cause": {
      "summary": "HikariCP连接获取超时（池压力）",
      "category": "infrastructure_resource_exhaustion",
      "confidence": 0.78
    },
    "evidence_chain": [
      {"type": "log", "description": "连接获取超时", "source": "CodeAgent", "strength": "strong"}
    ],
    "fix_recommendation": {
      "summary": "先采集连接池指标",
      "steps": ["采集 active/idle/waiting"],
      "code_changes_required": false
    },
    "impact_analysis": {"affected_services": ["order-service"], "business_impact": "下单失败"},
    "risk_assessment": {"risk_level": "high", "risk_factors": ["连接池资源不足"]}
  },
  "decision_rationale": {"reasoning": "综合结论
```"""

    payload = orchestrator._normalize_agent_output("JudgeAgent", raw)

    assert payload["final_judgment"]["root_cause"]["summary"] == "HikariCP连接获取超时（池压力）"
    assert payload["final_judgment"]["root_cause"]["category"] == "infrastructure_resource_exhaustion"
    assert payload["confidence"] >= 0.75


def test_judge_payload_recovery_wraps_nested_final_judgment_object():
    """验证裁决载荷恢复wrapsnestedfinaljudgmentobject。"""
    
    orchestrator = _orchestrator()
    raw = (
        '{"root_cause":{"summary":"数据库连接池耗尽","category":"db_pool","confidence":0.82},'
        '"evidence_chain":["连接获取超时30s"],'
        '"fix_recommendation":{"summary":"排查连接泄漏","steps":["检查连接关闭"],"code_changes_required":false},'
        '"risk_assessment":{"risk_level":"high","risk_factors":["连接池资源不足"]},'
        '"confidence":0.82}'
    )

    payload = orchestrator._normalize_agent_output("JudgeAgent", raw)

    assert payload["final_judgment"]["root_cause"]["summary"] == "数据库连接池耗尽"
    assert payload["confidence"] == 0.82


def test_build_final_payload_uses_best_agent_conclusion_when_judge_fallback():
    """验证buildfinal载荷使用bestAgent结论当裁决回退。"""
    
    orchestrator = _orchestrator()
    now = datetime.utcnow()
    code_output = {
        "analysis": "连接池等待队列增长，事务耗时过长",
        "conclusion": "订单创建链路出现连接池耗尽，需收敛事务边界并调优连接池配置",
        "evidence_chain": ["HikariPool timeout 30000ms", "OrderAppService#createOrder costMs=30058"],
        "confidence": 0.91,
    }
    judge_fallback = orchestrator._normalize_judge_output({}, "JudgeAgent 调用超时，已降级继续")

    orchestrator.turns = [
        DebateTurn(
            round_number=1,
            phase="analysis",
            agent_name="CodeAgent",
            agent_role="代码分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=code_output,
            confidence=0.91,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=2,
            phase="judgment",
            agent_name="JudgeAgent",
            agent_role="技术委员会主席",
            model={"name": "glm-5"},
            input_message="",
            output_content=judge_fallback,
            confidence=0.5,
            started_at=now,
            completed_at=now,
        ),
    ]
    history_cards = [
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码侧判断连接池等待过长",
            conclusion=code_output["conclusion"],
            evidence_chain=code_output["evidence_chain"],
            confidence=0.91,
            raw_output=code_output,
        )
    ]

    payload = orchestrator._build_final_payload(
        history_cards=history_cards,
        consensus_reached=False,
        executed_rounds=1,
    )

    summary = payload["final_judgment"]["root_cause"]["summary"]
    assert summary != orchestrator.JUDGE_FALLBACK_SUMMARY
    assert "连接池" in summary
    assert payload["confidence"] >= 0.55


def test_build_final_payload_caps_confidence_when_key_evidence_is_degraded():
    """验证buildfinal载荷capsconfidence当key证据is降级。"""
    
    orchestrator = _orchestrator()
    now = datetime.utcnow()
    judge_output = {
        "chat_message": "当前方向先按连接池耗尽处理。",
        "final_judgment": {
            "root_cause": {
                "summary": "连接池耗尽导致订单创建超时",
                "category": "db_resource_exhaustion",
                "confidence": 0.82,
            },
            "evidence_chain": [{"type": "analysis", "description": "单点日志证据", "source": "JudgeAgent"}],
            "fix_recommendation": {"summary": "先扩容", "steps": ["扩容连接池"], "code_changes_required": False},
            "impact_analysis": {"affected_services": ["order-service"], "business_impact": "下单失败"},
            "risk_assessment": {"risk_level": "medium", "risk_factors": []},
        },
        "decision_rationale": {"reasoning": "暂按已有方向收敛"},
        "action_items": [],
        "responsible_team": {"team": "order", "owner": "neo"},
        "confidence": 0.82,
    }
    orchestrator.turns = [
        DebateTurn(
            round_number=1,
            phase="analysis",
            agent_name="LogAgent",
            agent_role="日志分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content={
                "conclusion": "LogAgent 调用超时，已降级继续",
                "confidence": 0.45,
                "degraded": True,
                "evidence_status": "degraded",
            },
            confidence=0.45,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=2,
            phase="analysis",
            agent_name="DatabaseAgent",
            agent_role="数据库分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content={
                "conclusion": "DatabaseAgent 证据未采集完成：数据库工具未启用",
                "confidence": 0.22,
                "degraded": True,
                "evidence_status": "missing",
                "tool_status": "disabled",
            },
            confidence=0.22,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=3,
            phase="judgment",
            agent_name="JudgeAgent",
            agent_role="技术委员会主席",
            model={"name": "glm-5"},
            input_message="",
            output_content=judge_output,
            confidence=0.82,
            started_at=now,
            completed_at=now,
        ),
    ]
    history_cards = [
        AgentEvidence(
            agent_name="LogAgent",
            phase="analysis",
            summary="日志侧未完成",
            conclusion="LogAgent 调用超时，已降级继续",
            evidence_chain=[],
            confidence=0.45,
            raw_output=orchestrator.turns[0].output_content,
        ),
        AgentEvidence(
            agent_name="DatabaseAgent",
            phase="analysis",
            summary="数据库证据缺失",
            conclusion="DatabaseAgent 证据未采集完成：数据库工具未启用",
            evidence_chain=[],
            confidence=0.22,
            raw_output=orchestrator.turns[1].output_content,
        ),
    ]

    payload = orchestrator._build_final_payload(
        history_cards=history_cards,
        consensus_reached=False,
        executed_rounds=1,
    )

    assert payload["confidence"] <= 0.45
    risk_factors = payload["final_judgment"]["risk_assessment"]["risk_factors"]
    assert any("关键证据不足" in item for item in risk_factors)


def test_build_final_payload_keeps_medium_confidence_when_judge_has_strong_shared_evidence():
    """验证当 Judge 已拿到完整共享证据链时，不因部分专家降级而机械压到低置信。"""

    orchestrator = _orchestrator()
    now = datetime.utcnow()
    judge_output = {
        "chat_message": "我确认主因是 RiskService 同步调用重试耗尽主链路预算。",
        "final_judgment": {
            "root_cause": {
                "summary": "PaymentAppService 同步调用 RiskService，只有单次超时没有总超时预算与熔断，三次重试耗尽 30s 主链路预算。",
                "category": "upstream_timeout_budget_missing",
                "confidence": 0.76,
            },
            "evidence_chain": [
                {"type": "log", "description": "三次 RiskService timeout + 200ms backoff 累积约 30.4s", "source": "LogAgent", "strength": "strong"},
                {"type": "code", "description": "stacktrace 指向 RiskClient.check -> PaymentAppService.confirm", "source": "CodeAgent", "strength": "strong"},
                {"type": "metrics", "description": "Hikari active 4/30、DB CPU 18%、slow SQL 0，数据库不是原发根因", "source": "MetricsAgent", "strength": "strong"},
            ],
            "fix_recommendation": {
                "summary": "为 RiskService 调用增加总超时预算与熔断",
                "steps": ["限制重试总预算", "补熔断与快速失败"],
                "code_changes_required": True,
            },
            "impact_analysis": {"affected_services": ["payment-service"], "business_impact": "支付确认超时"},
            "risk_assessment": {"risk_level": "high", "risk_factors": ["上游同步调用超时放大"]},
        },
        "decision_rationale": {
            "reasoning": "stacktrace、重试时间线与数据库平稳指标相互印证，足以排除数据库主因。"
        },
        "action_items": [],
        "responsible_team": {"team": "payment", "owner": "neo"},
        "confidence": 0.76,
    }
    log_output = {
        "conclusion": "支付链路存在 3 次 10s 超时重试，累计时间接近 30s。",
        "confidence": 0.68,
        "evidence_status": "context_grounded_without_tool",
        "degraded": False,
    }
    metrics_output = {
        "conclusion": "数据库和连接池指标平稳，可排除数据库原发根因。",
        "confidence": 0.71,
        "evidence_status": "context_grounded_without_tool",
        "degraded": False,
    }
    code_timeout_output = {
        "conclusion": "CodeAgent 调用超时，已降级继续",
        "confidence": 0.45,
        "degraded": True,
        "evidence_status": "degraded",
    }
    db_missing_output = {
        "conclusion": "DatabaseAgent 证据未采集完成：数据库工具未启用",
        "confidence": 0.22,
        "degraded": True,
        "evidence_status": "missing",
        "tool_status": "disabled",
    }
    orchestrator.turns = [
        DebateTurn(
            round_number=1,
            phase="analysis",
            agent_name="LogAgent",
            agent_role="日志分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=log_output,
            confidence=0.68,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=2,
            phase="analysis",
            agent_name="MetricsAgent",
            agent_role="指标分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=metrics_output,
            confidence=0.71,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=3,
            phase="analysis",
            agent_name="CodeAgent",
            agent_role="代码分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=code_timeout_output,
            confidence=0.45,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=4,
            phase="analysis",
            agent_name="DatabaseAgent",
            agent_role="数据库分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=db_missing_output,
            confidence=0.22,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=5,
            phase="judgment",
            agent_name="JudgeAgent",
            agent_role="技术委员会主席",
            model={"name": "glm-5"},
            input_message="",
            output_content=judge_output,
            confidence=0.76,
            started_at=now,
            completed_at=now,
        ),
    ]
    history_cards = [
        AgentEvidence(
            agent_name="LogAgent",
            phase="analysis",
            summary="日志还原出 30s 重试时间线",
            conclusion=log_output["conclusion"],
            evidence_chain=["attempt1=10s", "attempt2=10s+200ms", "attempt3=10s+200ms"],
            confidence=0.68,
            raw_output=log_output,
        ),
        AgentEvidence(
            agent_name="MetricsAgent",
            phase="analysis",
            summary="数据库指标平稳",
            conclusion=metrics_output["conclusion"],
            evidence_chain=["Hikari 4/30", "DB CPU 18%", "slow SQL 0"],
            confidence=0.71,
            raw_output=metrics_output,
        ),
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码分析超时",
            conclusion=code_timeout_output["conclusion"],
            evidence_chain=[],
            confidence=0.45,
            raw_output=code_timeout_output,
        ),
        AgentEvidence(
            agent_name="DatabaseAgent",
            phase="analysis",
            summary="数据库工具缺失",
            conclusion=db_missing_output["conclusion"],
            evidence_chain=[],
            confidence=0.22,
            raw_output=db_missing_output,
        ),
    ]

    payload = orchestrator._build_final_payload(
        history_cards=history_cards,
        consensus_reached=False,
        executed_rounds=1,
    )

    assert payload["confidence"] >= 0.6
    assert payload["final_judgment"]["root_cause"]["summary"].startswith("PaymentAppService 同步调用 RiskService")
    risk_factors = payload["final_judgment"]["risk_assessment"]["risk_factors"]
    assert not any("关键证据不足" in item for item in risk_factors)


def test_build_final_payload_keeps_route_miss_judgment_above_low_confidence_floor():
    """网关本地 404 场景下，Judge 已有跨源强证据时不应再被压回 0.45。"""

    orchestrator = _orchestrator()
    now = datetime.utcnow()
    judge_output = {
        "chat_message": "我确认这是网关本地路由缺失，不是数据库或服务业务异常。",
        "final_judgment": {
            "root_cause": {
                "summary": "网关路由表未包含 POST /api/v1/orders，或服务注册中心未同步 order-service 实例，导致网关层直接返回 404。",
                "category": "infrastructure.gateway-route-miss",
                "confidence": 0.68,
            },
            "evidence_chain": [
                {
                    "type": "log",
                    "description": "网关日志显示 route not found path=/api/v1/orders method=POST return=404",
                    "source": "LogAgent",
                    "strength": "strong",
                },
                {
                    "type": "domain",
                    "description": "接口映射确认 POST /api/v1/orders 属于 OrderController#createOrder，说明服务契约存在。",
                    "source": "interface_mapping",
                    "strength": "strong",
                },
                {
                    "type": "code",
                    "description": "CodeAgent 确认 Controller 存在但运行时路由未注册到网关，可排除数据库不是原发根因。",
                    "source": "CodeAgent",
                    "strength": "strong",
                },
            ],
            "fix_recommendation": {
                "summary": "优先检查网关路由配置与服务注册状态",
                "steps": ["核对 gateway routes", "检查注册中心 order-service 健康状态"],
                "code_changes_required": False,
            },
            "impact_analysis": {"affected_services": ["gateway", "order-service"], "business_impact": "订单创建入口 404"},
            "risk_assessment": {"risk_level": "high", "risk_factors": ["缺少注册中心实时状态补证"]},
        },
        "decision_rationale": {
            "reasoning": "网关 route not found 日志、接口映射存在性与代码路径分析互相印证，足以排除数据库主因。"
        },
        "action_items": [],
        "responsible_team": {"team": "gateway-team", "owner": "alice"},
        "confidence": 0.68,
    }
    log_output = {
        "conclusion": "404 发生在 gateway route lookup 阶段，请求未转发到下游。",
        "confidence": 0.62,
        "evidence_status": "context_grounded_without_tool",
        "degraded": False,
    }
    code_output = {
        "conclusion": "OrderController#createOrder 存在，但运行时路由未正确注册到网关。",
        "confidence": 0.62,
        "evidence_status": "context_grounded_without_tool",
        "degraded": False,
    }
    domain_output = {
        "conclusion": "POST /api/v1/orders 归属 order-domain-team，但领域服务未被网关正确感知。",
        "confidence": 0.45,
        "degraded": True,
        "evidence_status": "degraded",
    }
    db_missing_output = {
        "conclusion": "数据库不是本次 404 的直接根因，但实时数据库证据未采集完成。",
        "confidence": 0.22,
        "degraded": True,
        "evidence_status": "missing",
        "tool_status": "disabled",
    }
    orchestrator.turns = [
        DebateTurn(
            round_number=1,
            phase="analysis",
            agent_name="LogAgent",
            agent_role="日志分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=log_output,
            confidence=0.62,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=2,
            phase="analysis",
            agent_name="CodeAgent",
            agent_role="代码分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=code_output,
            confidence=0.62,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=3,
            phase="analysis",
            agent_name="DomainAgent",
            agent_role="领域分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=domain_output,
            confidence=0.45,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=4,
            phase="analysis",
            agent_name="DatabaseAgent",
            agent_role="数据库分析专家",
            model={"name": "glm-5"},
            input_message="",
            output_content=db_missing_output,
            confidence=0.22,
            started_at=now,
            completed_at=now,
        ),
        DebateTurn(
            round_number=5,
            phase="judgment",
            agent_name="JudgeAgent",
            agent_role="技术委员会主席",
            model={"name": "glm-5"},
            input_message="",
            output_content=judge_output,
            confidence=0.68,
            started_at=now,
            completed_at=now,
        ),
    ]
    history_cards = [
        AgentEvidence(
            agent_name="LogAgent",
            phase="analysis",
            summary="日志确认 404 发生在网关本地路由查找阶段",
            conclusion=log_output["conclusion"],
            evidence_chain=["route not found", "return=404", "无下游 trace"],
            confidence=0.62,
            raw_output=log_output,
        ),
        AgentEvidence(
            agent_name="CodeAgent",
            phase="analysis",
            summary="代码与接口映射都说明端点存在",
            conclusion=code_output["conclusion"],
            evidence_chain=["OrderController#createOrder", "endpoint exists"],
            confidence=0.62,
            raw_output=code_output,
        ),
        AgentEvidence(
            agent_name="DomainAgent",
            phase="analysis",
            summary="领域侧需要注册中心补证",
            conclusion=domain_output["conclusion"],
            evidence_chain=[],
            confidence=0.45,
            raw_output=domain_output,
        ),
        AgentEvidence(
            agent_name="DatabaseAgent",
            phase="analysis",
            summary="数据库实时证据缺失",
            conclusion=db_missing_output["conclusion"],
            evidence_chain=[],
            confidence=0.22,
            raw_output=db_missing_output,
        ),
    ]

    payload = orchestrator._build_final_payload(
        history_cards=history_cards,
        consensus_reached=False,
        executed_rounds=1,
    )

    assert payload["confidence"] >= 0.6
    assert payload["final_judgment"]["root_cause"]["category"] == "infrastructure.gateway-route-miss"
    risk_factors = payload["final_judgment"]["risk_assessment"]["risk_factors"]
    assert not any("关键证据不足" in item for item in risk_factors)
