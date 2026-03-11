"""testlanggraph路由guardrail相关测试。"""

from app.config import settings
from app.runtime.langgraph.parsers import normalize_agent_output
from app.runtime.langgraph_runtime import LangGraphRuntimeOrchestrator
from app.runtime.messages import AgentEvidence


def _card(agent_name: str, phase: str, confidence: float = 0.6, **raw_output) -> AgentEvidence:
    """为测试场景提供卡片辅助逻辑。"""
    
    return AgentEvidence(
        agent_name=agent_name,
        phase=phase,
        summary=f"{agent_name} summary",
        conclusion=raw_output.get("conclusion", f"{agent_name} conclusion"),
        evidence_chain=[],
        confidence=confidence,
        raw_output=dict(raw_output),
    )


def test_route_guardrail_forces_judge_after_critique_cycle_when_parallel_requested(monkeypatch):
    """验证路由guardrailforces裁决后critiquecycle当并行requested。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", True)

    round_cards = [
        _card("ProblemAnalysisAgent", "analysis", 0.45, open_questions=["需要更多证据"]),
        _card("LogAgent", "analysis", 0.65),
        _card("DomainAgent", "analysis", 0.95),
        _card("CodeAgent", "analysis", 0.72),
        _card("ProblemAnalysisAgent", "analysis", 0.55, missing_info=["日志样本不足"]),
        _card("CriticAgent", "critique", 0.45),
        _card("ProblemAnalysisAgent", "analysis", 0.40, open_questions=["仍需交叉验证"]),
        _card("RebuttalAgent", "rebuttal", 0.40),
        _card("ProblemAnalysisAgent", "analysis", 0.40, open_questions=["再补一轮并行证据"]),
    ]
    state = {
        "discussion_step_count": 9,
        "max_discussion_steps": 12,
    }
    route_decision = {
        "next_step": "analysis_parallel",
        "should_stop": False,
        "stop_reason": "",
        "reason": "主Agent请求再次并行分析",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False


def test_route_guardrail_uses_agent_outputs_when_round_cards_missing(monkeypatch):
    """验证路由guardrail使用Agentoutputs当轮次cards缺失。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", True)

    # No ProblemAnalysisAgent/JudgeAgent cards in round_cards, only analyst cards.
    round_cards = [
        _card("LogAgent", "analysis", 0.65),
        _card("DomainAgent", "analysis", 0.72),
        _card("CodeAgent", "analysis", 0.70),
        _card("CriticAgent", "critique", 0.44),
        _card("RebuttalAgent", "rebuttal", 0.43),
    ]
    state = {
        "discussion_step_count": 9,
        "max_discussion_steps": 12,
        "agent_outputs": {
            "ProblemAnalysisAgent": {
                "confidence": 0.83,
                "open_questions": [],
                "missing_info": [],
            },
            "JudgeAgent": {"confidence": 0.20},
            "LogAgent": {"confidence": 0.65},
            "DomainAgent": {"confidence": 0.72},
            "CodeAgent": {"confidence": 0.70},
            "CriticAgent": {"confidence": 0.44},
            "RebuttalAgent": {"confidence": 0.43},
        },
    }
    route_decision = {
        "next_step": "analysis_parallel",
        "should_stop": False,
        "stop_reason": "",
        "reason": "主Agent请求再次并行分析",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False


def test_fallback_route_uses_agent_outputs_when_round_cards_empty(monkeypatch):
    """验证回退路由使用Agentoutputs当轮次cards空。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    decision = orchestrator._fallback_supervisor_route(
        state={
            "discussion_step_count": 3,
            "max_discussion_steps": 12,
            "agent_outputs": {
                "LogAgent": {"confidence": 0.66, "conclusion": "日志显示连接池获取超时"},
                "DomainAgent": {"confidence": 0.72},
                "CodeAgent": {"confidence": 0.70, "conclusion": "代码路径存在连接释放延迟"},
                "DatabaseAgent": {"confidence": 0.68, "conclusion": "数据库连接获取超时与锁等待并发出现"},
                "MetricsAgent": {"confidence": 0.63, "conclusion": "数据库等待时间与接口延迟同时升高"},
            },
        },
        round_cards=[],
    )

    assert decision["next_step"] == "analysis_parallel"
    assert decision["should_stop"] is False


def test_fallback_route_targets_gap_owner_when_open_question_is_specific(monkeypatch):
    """当未决问题已经指向数据库缺口时，应优先点名 DatabaseAgent。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    decision = orchestrator._fallback_supervisor_route(
        state={
            "discussion_step_count": 2,
            "max_discussion_steps": 10,
            "open_questions": ["数据库锁等待是否先于连接池耗尽出现"],
            "agent_outputs": {
                "LogAgent": {"confidence": 0.66, "conclusion": "日志显示连接获取超时"},
            },
        },
        round_cards=[
            _card(
                "ProblemAnalysisAgent",
                "analysis",
                0.35,
                open_questions=["数据库锁等待是否先于连接池耗尽出现"],
            ),
            _card("LogAgent", "analysis", 0.66, conclusion="日志显示连接获取超时"),
        ],
    )

    assert decision["next_step"] == "speak:DatabaseAgent"
    assert decision["should_stop"] is False


def test_route_guardrail_shortcuts_to_judge_after_full_parallel_revisit_without_critique(monkeypatch):
    """无批判模式下，四个基础分析专家都已给出有效证据时，不应再次整轮并行分析。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)
    orchestrator._enable_critique = False
    orchestrator.PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")

    round_cards = [
        _card(
            "LogAgent",
            "analysis",
            0.78,
            conclusion="日志时序已确认：promotionClient.checkQuota 1847ms 后立刻出现锁等待与连接池超时",
            evidence_chain=["10:08:09 promotionClient.checkQuota 1847ms", "10:08:10 waiting lock", "10:08:11 Hikari timeout"],
        ),
        _card(
            "DomainAgent",
            "analysis",
            0.74,
            conclusion="OrderAggregate 的事务边界设计有缺陷，远程调用不应在事务内",
            evidence_chain=["事务边界跨越远程调用"],
        ),
        _card(
            "CodeAgent",
            "analysis",
            0.83,
            conclusion="代码 diff 显示 promotionClient.checkQuota 从事务外移入 @Transactional createOrder",
            evidence_chain=["old flow 在 transactionTemplate.execute 之前", "new flow 在 @Transactional 内"],
        ),
        _card(
            "DatabaseAgent",
            "analysis",
            0.76,
            conclusion="数据库锁等待是长事务放大的结果，不是原发根因",
            evidence_chain=["row lock wait", "连接池耗尽晚于长事务"],
        ),
    ]
    state = {
        "discussion_step_count": 4,
        "max_discussion_steps": 8,
        "agent_outputs": {
            "ProblemAnalysisAgent": {
                "confidence": 0.52,
                "open_questions": [],
                "missing_info": [],
            },
            "LogAgent": {
                "confidence": 0.78,
                "conclusion": "日志时序已确认：promotionClient.checkQuota 1847ms 后立刻出现锁等待与连接池超时",
                "evidence_chain": ["10:08:09 promotionClient.checkQuota 1847ms"],
            },
            "DomainAgent": {
                "confidence": 0.74,
                "conclusion": "OrderAggregate 的事务边界设计有缺陷，远程调用不应在事务内",
                "evidence_chain": ["事务边界跨越远程调用"],
            },
            "CodeAgent": {
                "confidence": 0.83,
                "conclusion": "代码 diff 显示 promotionClient.checkQuota 从事务外移入 @Transactional createOrder",
                "evidence_chain": ["old flow 在 transactionTemplate.execute 之前"],
            },
            "DatabaseAgent": {
                "confidence": 0.76,
                "conclusion": "数据库锁等待是长事务放大的结果，不是原发根因",
                "evidence_chain": ["row lock wait"],
            },
        },
    }
    route_decision = {
        "next_step": "analysis_parallel",
        "should_stop": False,
        "stop_reason": "",
        "reason": "主Agent要求再做一轮并行分析",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False


def test_route_guardrail_accepts_normalized_domain_payload_from_nested_analysis(monkeypatch):
    """无批判模式下，DomainAgent 的嵌套分析被抬平后应算作有效覆盖。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)
    orchestrator._enable_critique = False
    orchestrator.PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")

    normalized_domain = normalize_agent_output(
        "DomainAgent",
        """```json
{
  "chat_message": "领域边界判断已完成。",
  "domain_analysis": {
    "business_transaction_boundary": {
      "violation_type": "事务边界过长——远程RPC同步调用内嵌事务"
    },
    "root_cause_evidence": {
      "log_timestamp_chain": [
        "10:08:09 promotionClient.checkQuota cost=1847ms",
        "10:08:10 inventory lock wait txId=7812231"
      ],
      "causal_inference": "远程调用耗时1847ms -> 事务持有连接 -> 锁等待"
    },
    "confidence": 0.85
  }
}
```""",
        judge_fallback_summary="fallback",
    )

    round_cards = [
        _card(
            "LogAgent",
            "analysis",
            0.79,
            conclusion="日志链路已确认：远程调用后出现锁等待与连接池超时",
            evidence_chain=["10:08:09 promotionClient.checkQuota 1847ms"],
        ),
        _card(
            "CodeAgent",
            "analysis",
            0.84,
            conclusion="代码 diff 显示 promotionClient.checkQuota 从事务外移入 @Transactional",
            evidence_chain=["new flow 在 @Transactional 内"],
        ),
        _card(
            "DatabaseAgent",
            "analysis",
            0.76,
            conclusion="数据库锁等待是长事务放大的结果，不是原发根因",
            evidence_chain=["row lock wait"],
        ),
    ]
    state = {
        "discussion_step_count": 4,
        "max_discussion_steps": 8,
        "agent_outputs": {
            "ProblemAnalysisAgent": {"confidence": 0.48, "open_questions": [], "missing_info": []},
            "LogAgent": {
                "confidence": 0.79,
                "conclusion": "日志链路已确认：远程调用后出现锁等待与连接池超时",
                "evidence_chain": ["10:08:09 promotionClient.checkQuota 1847ms"],
            },
            "DomainAgent": normalized_domain,
            "CodeAgent": {
                "confidence": 0.84,
                "conclusion": "代码 diff 显示 promotionClient.checkQuota 从事务外移入 @Transactional",
                "evidence_chain": ["new flow 在 @Transactional 内"],
            },
            "DatabaseAgent": {
                "confidence": 0.76,
                "conclusion": "数据库锁等待是长事务放大的结果，不是原发根因",
                "evidence_chain": ["row lock wait"],
            },
        },
    }
    route_decision = {
        "next_step": "analysis_parallel",
        "should_stop": False,
        "stop_reason": "",
        "reason": "主Agent请求再次并行分析",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert normalized_domain["confidence"] == 0.85
    assert len(normalized_domain["evidence_chain"]) >= 2
    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False


def test_route_guardrail_accepts_context_grounded_without_tool_outputs(monkeypatch):
    """工具受限但共享证据已充分时，路由不应把专家输出当成硬降级继续重跑。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)
    orchestrator._enable_critique = False
    orchestrator.PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")

    route_decision = {
        "next_step": "analysis_parallel",
        "should_stop": False,
        "stop_reason": "",
        "reason": "继续并行分析",
    }
    state = {
        "discussion_step_count": 4,
        "max_discussion_steps": 8,
        "agent_outputs": {
            "ProblemAnalysisAgent": {"confidence": 0.48, "open_questions": [], "missing_info": []},
            "LogAgent": {
                "confidence": 0.71,
                "conclusion": "日志显示 promotionClient.checkQuota 延迟抬升后出现 Hikari 超时",
                "evidence_chain": ["promotion latency spike", "Hikari timeout"],
                "evidence_status": "context_grounded_without_tool",
                "tool_limited": True,
            },
            "DomainAgent": {
                "confidence": 0.69,
                "conclusion": "订单域事务边界跨越远程调用，不符合领域职责拆分",
                "evidence_chain": ["聚合根事务边界异常"],
            },
            "CodeAgent": {
                "confidence": 0.72,
                "conclusion": "code diff 显示 promotionClient.checkQuota 被移入 @Transactional createOrder",
                "evidence_chain": ["code diff summary", "@Transactional createOrder"],
                "evidence_status": "context_grounded_without_tool",
                "tool_limited": True,
            },
            "DatabaseAgent": {
                "confidence": 0.68,
                "conclusion": "数据库锁等待是长事务放大的结果，不是原发根因",
                "evidence_chain": ["row lock wait after promotion latency spike"],
                "evidence_status": "context_grounded_without_tool",
                "tool_limited": True,
            },
        },
    }
    round_cards = [
        _card(
            "LogAgent",
            "analysis",
            0.71,
            conclusion="日志显示 promotionClient.checkQuota 延迟抬升后出现 Hikari 超时",
            evidence_chain=["promotion latency spike", "Hikari timeout"],
            evidence_status="context_grounded_without_tool",
            tool_limited=True,
        ),
        _card(
            "DomainAgent",
            "analysis",
            0.69,
            conclusion="订单域事务边界跨越远程调用，不符合领域职责拆分",
            evidence_chain=["聚合根事务边界异常"],
        ),
        _card(
            "CodeAgent",
            "analysis",
            0.72,
            conclusion="code diff 显示 promotionClient.checkQuota 被移入 @Transactional createOrder",
            evidence_chain=["code diff summary", "@Transactional createOrder"],
            evidence_status="context_grounded_without_tool",
            tool_limited=True,
        ),
        _card(
            "DatabaseAgent",
            "analysis",
            0.68,
            conclusion="数据库锁等待是长事务放大的结果，不是原发根因",
            evidence_chain=["row lock wait after promotion latency spike"],
            evidence_status="context_grounded_without_tool",
            tool_limited=True,
        ),
    ]

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False


def test_route_guardrail_shortcuts_to_judge_when_targeted_reask_hits_already_effective_agent(monkeypatch):
    """无批判模式下，若定向追问的专家已经形成有效覆盖，应直接切 Judge。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)
    orchestrator._enable_critique = False
    orchestrator.PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")

    round_cards = [
        _card(
            "ProblemAnalysisAgent",
            "analysis",
            0.58,
            conclusion="三位关键专家都已指向同一条链路，剩余主要是工具补证。",
            open_questions=["需要日志工具补拉完整 trace"],
        ),
        _card(
            "LogAgent",
            "analysis",
            0.72,
            conclusion="日志时间线已确认：promotion latency -> waiting lock -> Hikari timeout -> 502",
            evidence_status="context_grounded_without_tool",
            tool_limited=True,
        ),
        _card(
            "DomainAgent",
            "analysis",
            0.69,
            conclusion="订单域事务边界跨越远程调用，违反聚合根边界原则。",
        ),
        _card(
            "CodeAgent",
            "analysis",
            0.74,
            conclusion="代码路径已指向 @Transactional 覆盖 promotionClient.checkQuota。",
            evidence_status="context_grounded_without_tool",
            tool_limited=True,
        ),
        _card(
            "DatabaseAgent",
            "analysis",
            0.71,
            conclusion="数据库锁等待是长事务放大的结果，不是原发根因。",
            evidence_status="context_grounded_without_tool",
            tool_limited=True,
        ),
    ]
    state = {
        "discussion_step_count": 5,
        "max_discussion_steps": 8,
        "agent_outputs": {
            "ProblemAnalysisAgent": {
                "confidence": 0.58,
                "open_questions": ["需要日志工具补拉完整 trace"],
                "missing_info": [],
            },
            "LogAgent": {
                "confidence": 0.72,
                "conclusion": "日志时间线已确认：promotion latency -> waiting lock -> Hikari timeout -> 502",
                "evidence_status": "context_grounded_without_tool",
                "tool_limited": True,
            },
            "DomainAgent": {
                "confidence": 0.69,
                "conclusion": "订单域事务边界跨越远程调用，违反聚合根边界原则。",
            },
            "CodeAgent": {
                "confidence": 0.74,
                "conclusion": "代码路径已指向 @Transactional 覆盖 promotionClient.checkQuota。",
                "evidence_status": "context_grounded_without_tool",
                "tool_limited": True,
            },
            "DatabaseAgent": {
                "confidence": 0.71,
                "conclusion": "数据库锁等待是长事务放大的结果，不是原发根因。",
                "evidence_status": "context_grounded_without_tool",
                "tool_limited": True,
            },
        },
    }
    route_decision = {
        "next_step": "speak:LogAgent",
        "should_stop": False,
        "stop_reason": "",
        "reason": "补拉日志 trace 以确认事务边界",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False


def test_route_guardrail_shortcuts_route_miss_cases_to_judge(monkeypatch):
    """网关本地 404 路由缺失场景下，不应继续重复追问专家。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)
    orchestrator._enable_critique = False
    orchestrator.PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")

    round_cards = [
        _card(
            "ProblemAnalysisAgent",
            "analysis",
            0.62,
            conclusion="当前证据已集中指向网关本地 404 路由缺失，数据库并非主因。",
            open_questions=["补确认是否为服务未注册或端点未暴露"],
        ),
        _card(
            "LogAgent",
            "analysis",
            0.78,
            conclusion="网关日志明确出现 route not found，404 在网关本地返回，并未转发到下游服务。",
            evidence_chain=["gateway route not found", "return=404", "无 upstream 调用"],
        ),
        _card(
            "DomainAgent",
            "analysis",
            0.73,
            conclusion="订单创建链路未进入下游业务域，故障更符合网关本地路由缺失或服务未注册。",
            evidence_chain=["未进入订单服务", "服务发现或路由配置缺口"],
        ),
        _card(
            "CodeAgent",
            "analysis",
            0.71,
            conclusion="接口 /api/v1/orders 在当前网关路由表中未暴露，疑似端点未注册或路由规则未同步。",
            evidence_chain=["gateway route config missing", "endpoint not exposed"],
        ),
        _card(
            "DatabaseAgent",
            "analysis",
            0.66,
            conclusion="数据库没有参与本次 404 返回链路，不是原发根因。",
            evidence_chain=["无 SQL 执行", "无连接池抖动"],
        ),
    ]
    state = {
        "discussion_step_count": 5,
        "max_discussion_steps": 8,
        "agent_outputs": {
            "ProblemAnalysisAgent": {
                "confidence": 0.62,
                "conclusion": "当前证据已集中指向网关本地 404 路由缺失，数据库并非主因。",
                "open_questions": ["补确认是否为服务未注册或端点未暴露"],
                "missing_info": [],
            },
            "LogAgent": {
                "confidence": 0.78,
                "conclusion": "网关日志明确出现 route not found，404 在网关本地返回，并未转发到下游服务。",
                "evidence_chain": ["gateway route not found", "return=404", "无 upstream 调用"],
            },
            "DomainAgent": {
                "confidence": 0.73,
                "conclusion": "订单创建链路未进入下游业务域，故障更符合网关本地路由缺失或服务未注册。",
                "evidence_chain": ["未进入订单服务", "服务发现或路由配置缺口"],
            },
            "CodeAgent": {
                "confidence": 0.71,
                "conclusion": "接口 /api/v1/orders 在当前网关路由表中未暴露，疑似端点未注册或路由规则未同步。",
                "evidence_chain": ["gateway route config missing", "endpoint not exposed"],
            },
            "DatabaseAgent": {
                "confidence": 0.66,
                "conclusion": "数据库没有参与本次 404 返回链路，不是原发根因。",
                "evidence_chain": ["无 SQL 执行", "无连接池抖动"],
            },
        },
    }
    route_decision = {
        "next_step": "speak:CodeAgent",
        "should_stop": False,
        "stop_reason": "",
        "reason": "继续追问 CodeAgent 补充代码级证据",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:JudgeAgent"
    assert guarded["should_stop"] is False


def test_route_guardrail_redirects_parallel_revisit_to_gap_owner_without_critique(monkeypatch):
    """无批判模式下，若缺口已明确指向单个专家，不应再次整轮并行分析。"""

    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)
    orchestrator._enable_critique = False
    orchestrator.PARALLEL_ANALYSIS_AGENTS = ("LogAgent", "DomainAgent", "CodeAgent", "DatabaseAgent")

    round_cards = [
        _card(
            "LogAgent",
            "analysis",
            0.79,
            conclusion="日志时序已确认：远程调用后立刻进入锁等待与连接池超时",
            evidence_chain=["10:08:09 promotionClient.checkQuota 1847ms", "10:08:11 Hikari timeout"],
        ),
        _card(
            "CodeAgent",
            "analysis",
            0.84,
            conclusion="代码 diff 已确认远程调用从事务外移入 @Transactional",
            evidence_chain=["old flow 在 transactionTemplate.execute 之前", "new flow 在 @Transactional 内"],
        ),
        _card(
            "DatabaseAgent",
            "analysis",
            0.76,
            conclusion="数据库锁等待是长事务放大的结果，不是原发根因",
            evidence_chain=["row lock wait", "连接池耗尽晚于长事务"],
        ),
    ]
    state = {
        "discussion_step_count": 6,
        "max_discussion_steps": 10,
        "open_questions": ["仍需确认该远程调用在领域边界上是否必须位于事务内"],
        "round_gap_summary": ["领域边界尚未收敛，需要 DomainAgent 给出是否可外移的判断。"],
        "agent_outputs": {
            "ProblemAnalysisAgent": {
                "confidence": 0.61,
                "open_questions": ["仍需确认该远程调用在领域边界上是否必须位于事务内"],
            },
            "LogAgent": {
                "confidence": 0.79,
                "conclusion": "日志时序已确认：远程调用后立刻进入锁等待与连接池超时",
                "evidence_chain": ["10:08:09 promotionClient.checkQuota 1847ms"],
            },
            "CodeAgent": {
                "confidence": 0.84,
                "conclusion": "代码 diff 已确认远程调用从事务外移入 @Transactional",
                "evidence_chain": ["new flow 在 @Transactional 内"],
            },
            "DatabaseAgent": {
                "confidence": 0.76,
                "conclusion": "数据库锁等待是长事务放大的结果，不是原发根因",
                "evidence_chain": ["row lock wait"],
            },
        },
    }
    route_decision = {
        "next_step": "analysis_parallel",
        "should_stop": False,
        "stop_reason": "",
        "reason": "主Agent要求再做一轮并行分析",
    }

    guarded = orchestrator._route_guardrail(
        state=state,
        round_cards=round_cards,
        route_decision=route_decision,
    )

    assert guarded["next_step"] == "speak:DomainAgent"
    assert guarded["should_stop"] is False


def test_commander_route_stops_after_effective_judge_when_next_agent_only_retries_degraded_evidence(monkeypatch):
    """验证主Agent路由stops后有效裁决当nextAgentonlyretries降级证据。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    round_cards = [
        _card(
            "JudgeAgent",
            "judgment",
            0.46,
            final_judgment={
                "root_cause": {
                    "summary": "数据库连接池(HikariPool)连接获取超时",
                    "confidence": 0.46,
                }
            },
            conclusion="数据库连接池(HikariPool)连接获取超时",
        ),
        _card(
            "ProblemAnalysisAgent",
            "judgment",
            0.42,
            conclusion="当前结论：数据库连接池(HikariPool)连接获取超时",
        ),
        _card(
            "DatabaseAgent",
            "analysis",
            0.18,
            conclusion="DatabaseAgent 调用超时，已降级继续",
            degraded=True,
            evidence_status="degraded",
            tool_status="timeout",
        ),
    ]

    decision = orchestrator._route_from_commander_output(
        payload={
            "next_mode": "single",
            "next_agent": "DatabaseAgent",
            "should_stop": False,
            "stop_reason": "",
        },
        state={
            "discussion_step_count": 9,
            "max_discussion_steps": 10,
            "agent_outputs": {
                "JudgeAgent": {
                    "final_judgment": {
                        "root_cause": {
                            "summary": "数据库连接池(HikariPool)连接获取超时",
                            "confidence": 0.46,
                        }
                    }
                },
                "ProblemAnalysisAgent": {
                    "conclusion": "当前结论：数据库连接池(HikariPool)连接获取超时",
                    "confidence": 0.42,
                },
                "DatabaseAgent": {
                    "conclusion": "DatabaseAgent 调用超时，已降级继续",
                    "degraded": True,
                    "evidence_status": "degraded",
                },
            },
        },
        round_cards=round_cards,
    )

    assert decision["should_stop"] is True
    assert decision["next_step"] == ""


def test_commander_route_keeps_collecting_when_judge_not_yet_actionable(monkeypatch):
    """验证主Agent路由保留collecting当裁决notyetactionable。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    round_cards = [
        _card(
            "JudgeAgent",
            "judgment",
            0.28,
            final_judgment={
                "root_cause": {
                    "summary": "仍需补充日志与代码证据",
                    "confidence": 0.28,
                }
            },
            conclusion="仍需补充日志与代码证据",
        ),
        _card(
            "ProblemAnalysisAgent",
            "analysis",
            0.34,
            open_questions=["日志样本不足", "代码入口未确认"],
        ),
    ]

    decision = orchestrator._route_from_commander_output(
        payload={
            "next_mode": "single",
            "next_agent": "LogAgent",
            "should_stop": False,
            "stop_reason": "",
        },
        state={
            "discussion_step_count": 4,
            "max_discussion_steps": 10,
            "agent_outputs": {
                "JudgeAgent": {
                    "final_judgment": {
                        "root_cause": {
                            "summary": "仍需补充日志与代码证据",
                            "confidence": 0.28,
                        }
                    }
                },
                "ProblemAnalysisAgent": {
                    "open_questions": ["日志样本不足", "代码入口未确认"],
                    "confidence": 0.34,
                },
            },
        },
        round_cards=round_cards,
    )

    assert decision["should_stop"] is False
    assert decision["next_step"] == "speak:LogAgent"


def test_commander_route_stops_after_effective_judge_when_commander_already_summarized(monkeypatch):
    """验证主Agent路由stops后有效裁决当主Agentalreadysummarized。"""
    
    orchestrator = LangGraphRuntimeOrchestrator(consensus_threshold=0.75, max_rounds=1)
    monkeypatch.setattr(settings, "DEBATE_ENABLE_CRITIQUE", False)

    round_cards = [
        _card(
            "JudgeAgent",
            "judgment",
            0.51,
            final_judgment={
                "root_cause": {
                    "summary": "订单定价链路中数据库连接池获取超时",
                    "confidence": 0.51,
                }
            },
            conclusion="订单定价链路中数据库连接池获取超时",
        ),
        _card(
            "ProblemAnalysisAgent",
            "judgment",
            0.48,
            conclusion="我已汇总各专家反馈，当前结论：订单定价链路中数据库连接池获取超时",
        ),
    ]

    decision = orchestrator._route_from_commander_output(
        payload={
            "next_mode": "single",
            "next_agent": "LogAgent",
            "should_stop": False,
            "stop_reason": "",
        },
        state={
            "discussion_step_count": 8,
            "max_discussion_steps": 10,
            "agent_outputs": {
                "JudgeAgent": {
                    "final_judgment": {
                        "root_cause": {
                            "summary": "订单定价链路中数据库连接池获取超时",
                            "confidence": 0.51,
                        }
                    }
                },
                "ProblemAnalysisAgent": {
                    "conclusion": "我已汇总各专家反馈，当前结论：订单定价链路中数据库连接池获取超时",
                    "confidence": 0.48,
                },
            },
        },
        round_cards=round_cards,
    )

    assert decision["should_stop"] is True
    assert decision["next_step"] == ""
