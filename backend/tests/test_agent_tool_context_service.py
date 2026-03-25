"""testAgent工具上下文服务相关测试。"""

from __future__ import annotations

import sqlite3
import subprocess

import pytest

from app.models.knowledge import KnowledgeEntry, KnowledgeEntryType, RunbookFields
from app.models.tooling import (
    AgentSkillConfig,
    AgentToolPluginConfig,
    AgentToolingConfig,
    DatabaseToolConfig,
)
from app.services.agent_tool_context_service import AgentToolContextService


def test_collect_recent_git_changes_handles_repo_without_commits(tmp_path):
    """验证collect最近Git变更处理repo无commits。"""
    
    subprocess.run(
        ["git", "init"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )

    service = AgentToolContextService()
    audit_log = []
    changes = service._collect_recent_git_changes(  # noqa: SLF001 - testing internal fallback behavior
        str(tmp_path),
        20,
        audit_log,
    )

    assert changes == []
    assert any(
        str(item.get("action") or "") == "git_log_changes" and str(item.get("status") or "") == "unavailable"
        for item in audit_log
    )


def test_extract_keywords_uses_investigation_leads():
    """验证提取关键词使用investigation线索。"""
    
    service = AgentToolContextService()

    keywords = service._extract_keywords(  # noqa: SLF001 - validating lead expansion logic
        {
            "log_excerpt": "timeout on orders",
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "class_names": ["OrderController", "OrderService"],
                "code_artifacts": ["order/service/OrderService.java"],
                "database_tables": ["t_order"],
                "monitor_items": ["order.error.rate"],
                "dependency_services": ["inventory-service"],
                "trace_ids": ["trace-001"],
                "error_keywords": ["timeout"],
            },
        },
        {},
        {"task": "根据已知线索定位问题"},
    )

    assert "orders" in keywords
    assert "order-service" in keywords
    assert "ordercontroller" in keywords
    assert "t_order" in keywords
    assert "inventory-service" in keywords


def test_build_code_focused_context_includes_entrypoint_and_hits(tmp_path):
    """验证 CodeAgent focused context 会包含入口与代码窗口。"""

    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "src" / "order"
    target.mkdir(parents=True)
    source = target / "OrderController.java"
    source.write_text(
        "@PostMapping(\"/api/v1/orders\")\npublic class OrderController {\n  void createOrder() {}\n}\n",
        encoding="utf-8",
    )

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="CodeAgent",
        compact_context={
            "interface_mapping": {
                "endpoint": {"method": "POST", "path": "/api/v1/orders", "service": "order-service"},
                "code_artifacts": ["src/order/OrderController.java"],
            },
            "investigation_leads": {
                "class_names": ["OrderController"],
                "code_artifacts": ["src/order/OrderController.java"],
            },
        },
        incident_context={"description": "/orders 502"},
        tool_context={
            "data": {
                "repo_path": str(repo),
                "hits": [
                    {
                        "file": "src/order/OrderController.java",
                        "line": 1,
                        "keyword": "orders",
                        "snippet": "@PostMapping(\"/api/v1/orders\")",
                    }
                ]
            }
        },
        assigned_command={"task": "分析接口调用链", "focus": "controller -> service"},
    )

    assert focused["problem_entrypoint"]["path"] == "/api/v1/orders"
    assert focused["repo_hits"]["match_count"] == 1
    assert focused["code_windows"][0]["file"] == "src/order/OrderController.java"


def test_build_code_focused_context_expands_to_related_call_chain_files(tmp_path):
    """验证 CodeAgent focused context 会从接口入口继续展开关联调用文件。"""

    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "src" / "order"
    src.mkdir(parents=True)
    (src / "OrderController.java").write_text(
        (
            "@RestController\n"
            "public class OrderController {\n"
            "  private final OrderService orderService;\n"
            "  public void create() { orderService.createOrder(); }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (src / "OrderService.java").write_text(
        (
            "public class OrderService {\n"
            "  private final OrderRepository orderRepository;\n"
            "  public void createOrder() { orderRepository.save(); }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (src / "OrderRepository.java").write_text(
        "public class OrderRepository { public void save() {} }\n",
        encoding="utf-8",
    )

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="CodeAgent",
        compact_context={
            "interface_mapping": {
                "endpoint": {"method": "POST", "path": "/api/v1/orders", "service": "order-service"},
                "code_artifacts": ["src/order/OrderController.java"],
            },
            "investigation_leads": {
                "class_names": ["OrderController", "OrderService"],
                "code_artifacts": ["src/order/OrderController.java"],
            },
        },
        incident_context={"description": "/orders 502"},
        tool_context={
            "data": {
                "repo_path": str(repo),
                "hits": [
                    {
                        "file": "src/order/OrderController.java",
                        "line": 3,
                        "keyword": "orders",
                        "snippet": "private final OrderService orderService;",
                    }
                ]
            }
        },
        assigned_command={"task": "分析接口调用链", "focus": "controller -> service -> repository"},
    )

    files = [item["file"] for item in focused["code_windows"]]
    assert "src/order/OrderController.java" in files
    assert "src/order/OrderService.java" in files


def test_build_code_focused_context_includes_method_level_call_chain(tmp_path):
    """验证 CodeAgent focused context 会输出方法级调用链摘要。"""

    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "src" / "order"
    src.mkdir(parents=True)
    (src / "OrderController.java").write_text(
        (
            "@PostMapping(\"/api/v1/orders\")\n"
            "public class OrderController {\n"
            "  private final OrderService orderService;\n"
            "  public void createOrder() {\n"
            "    orderService.createOrder();\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (src / "OrderService.java").write_text(
        (
            "public class OrderService {\n"
            "  private final OrderRepository orderRepository;\n"
            "  public void createOrder() {\n"
            "    orderRepository.saveOrder();\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (src / "OrderRepository.java").write_text(
        (
            "public class OrderRepository {\n"
            "  public void saveOrder() {}\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="CodeAgent",
        compact_context={
            "interface_mapping": {
                "endpoint": {
                    "method": "POST",
                    "path": "/api/v1/orders",
                    "service": "order-service",
                    "interface": "OrderController#createOrder",
                },
                "code_artifacts": ["src/order/OrderController.java"],
            },
            "investigation_leads": {
                "class_names": ["OrderController", "OrderService", "OrderRepository"],
                "code_artifacts": ["src/order/OrderController.java"],
            },
        },
        incident_context={"description": "/orders 502"},
        tool_context={
            "data": {
                "repo_path": str(repo),
                "hits": [
                    {
                        "file": "src/order/OrderController.java",
                        "line": 4,
                        "keyword": "createorder",
                        "snippet": "orderService.createOrder();",
                    }
                ]
            }
        },
        assigned_command={"task": "分析方法调用链", "focus": "createOrder -> saveOrder"},
    )

    chain = focused["method_call_chain"]
    assert len(chain) >= 2
    assert chain[0]["method"] == "createOrder"
    assert "OrderController" in chain[0]["symbol"]
    assert any(item["method"] == "saveOrder" for item in chain)


def test_build_code_focused_context_includes_topology_summaries(tmp_path):
    """验证 CodeAgent focused context 会输出调用图、SQL、RPC、事务与资源风险摘要。"""

    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "src" / "order"
    src.mkdir(parents=True)
    (src / "OrderController.java").write_text(
        (
            "@RestController\n"
            "public class OrderController {\n"
            "  private final OrderService orderService;\n"
            "  public void createOrder() { orderService.createOrder(); }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (src / "OrderService.java").write_text(
        (
            "public class OrderService {\n"
            "  private final OrderRepository orderRepository;\n"
            "  private final InventoryClient inventoryClient;\n"
            "  @Transactional\n"
            "  public void createOrder() {\n"
            "    inventoryClient.deduct();\n"
            "    orderRepository.saveOrder();\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (src / "OrderRepository.java").write_text(
        (
            "public class OrderRepository {\n"
            "  @Query(\"update t_order set status='OK' where id=?\")\n"
            "  public void saveOrder() {}\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (src / "InventoryClient.java").write_text(
        (
            "@FeignClient(name = \"inventory-service\")\n"
            "public interface InventoryClient {\n"
            "  void deduct();\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="CodeAgent",
        compact_context={
            "interface_mapping": {
                "endpoint": {
                    "method": "POST",
                    "path": "/api/v1/orders",
                    "service": "order-service",
                    "interface": "OrderController#createOrder",
                },
                "code_artifacts": ["src/order/OrderController.java"],
                "dependency_services": ["inventory-service"],
                "database_tables": ["t_order"],
            },
            "investigation_leads": {
                "class_names": ["OrderController", "OrderService", "OrderRepository", "InventoryClient"],
                "code_artifacts": ["src/order/OrderController.java"],
                "dependency_services": ["inventory-service"],
                "database_tables": ["t_order"],
            },
        },
        incident_context={"description": "/orders 502"},
        tool_context={
            "data": {
                "repo_path": str(repo),
                "hits": [
                    {
                        "file": "src/order/OrderController.java",
                        "line": 4,
                        "keyword": "createorder",
                        "snippet": "orderService.createOrder();",
                    }
                ]
            }
        },
        assigned_command={"task": "分析接口拓扑闭包", "focus": "controller -> service -> dao -> rpc"},
    )

    assert focused["call_graph_summary"]["entry_method"] == "OrderController#createOrder"
    assert "OrderRepository#saveOrder" in focused["call_graph_summary"]["call_path"]
    assert "t_order" in focused["sql_binding_summary"]["matched_tables"]
    assert focused["downstream_rpc_summary"]["dependency_services"] == ["inventory-service"]
    assert "同步下游调用可能阻塞" in focused["resource_risk_points"]
    assert focused["transaction_boundary_summary"]["boundary_hints"]


def test_build_database_focused_context_includes_sql_and_tables():
    """验证 DatabaseAgent focused context 会包含目标表和 SQL 摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="DatabaseAgent",
        compact_context={
            "interface_mapping": {"database_tables": ["public.t_order"]},
        },
        incident_context={"description": "/orders 502"},
        tool_context={
            "data": {
                "engine": "postgresql",
                "schema": "public",
                "tables": ["t_order"],
                "table_structures": [{"table": "t_order", "columns": [{"name": "id"}]}],
                "indexes": {"t_order": [{"index": "idx_order_status"}]},
                "slow_sql": [{"query": "select * from t_order", "mean_exec_time": 30}],
                "session_status": [{"state": "active", "sessions": 10}],
            }
        },
        assigned_command={"task": "分析锁等待", "database_tables": ["public.t_order"]},
    )

    assert focused["target_tables"] == ["public.t_order"]
    assert focused["schema_summary"]["engine"] == "postgresql"
    assert len(focused["sql_signals"]["slow_sql"]) == 1


def test_build_domain_focused_context_includes_causal_summary():
    """验证 DomainAgent focused context 会输出责任归属与影响边界摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="DomainAgent",
        compact_context={
            "interface_mapping": {
                "matched": True,
                "confidence": 0.92,
                "domain": "交易域",
                "aggregate": "订单聚合",
                "owner_team": "order-domain-team",
                "owner": "alice",
                "feature": "订单创建",
                "database_tables": ["public.t_order", "public.t_order_item"],
                "dependency_services": ["inventory-service", "gateway-service"],
                "monitor_items": ["order.5xx", "db.pool.pending"],
                "endpoint": {
                    "method": "POST",
                    "path": "/api/v1/orders",
                    "service": "order-service",
                },
            }
        },
        incident_context={"description": "/orders 502"},
        tool_context={
            "data": {
                "matches": [
                    {
                        "feature": "订单创建",
                        "domain": "交易域",
                        "aggregate": "订单聚合",
                        "owner_team": "order-domain-team",
                    }
                ]
            }
        },
        assigned_command={"task": "确认责任归属与影响边界", "focus": "下游依赖与数据库表"},
    )

    summary = focused["causal_summary"]
    assert summary["dominant_pattern"] in {"owner_confirmed", "mapping_gap"}
    assert summary["owner_team"] == "order-domain-team"
    assert "public.t_order" in summary["impact_scope"]["database_tables"]
    assert len(summary["impact_scope"]["dependency_services"]) >= 1
    assert len(summary["evidence_points"]) >= 2


def test_build_domain_focused_context_includes_constraint_checks():
    """验证 DomainAgent focused context 会输出聚合约束与领域检查项。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="DomainAgent",
        compact_context={
            "interface_mapping": {
                "matched": True,
                "domain": "交易域",
                "aggregate": "订单聚合",
                "owner_team": "order-domain-team",
                "feature": "订单创建",
                "database_tables": ["public.t_order"],
                "dependency_services": ["inventory-service"],
                "endpoint": {"method": "POST", "path": "/api/v1/orders", "service": "order-service"},
            }
        },
        incident_context={"description": "/orders 502"},
        tool_context={"data": {"matches": [{"feature": "订单创建"}]}},
        assigned_command={"task": "检查领域约束", "focus": "聚合不变量与事务顺序"},
    )

    assert focused["aggregate_invariants"]
    assert any(item["name"] == "transaction_order" for item in focused["domain_constraint_checks"])


def test_build_problem_analysis_focused_context_includes_coordination_summary():
    """验证 ProblemAnalysisAgent focused context 会输出主控调度摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="ProblemAnalysisAgent",
        compact_context={
            "incident_summary": {
                "title": "/api/v1/orders 接口 502 + CPU 飙高",
                "description": "订单接口 502，数据库连接池 pending 高，CPU 持续飙升",
                "severity": "high",
                "service_name": "order-service",
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "database_tables": ["public.t_order", "public.t_order_item"],
                "error_keywords": ["502", "timeout", "db lock"],
                "trace_ids": ["trc-001"],
            },
        },
        incident_context={"description": "/orders 502 cpu high db lock"},
        tool_context={"name": "rule_suggestion_bundle", "status": "ok", "summary": "已汇总规则建议与案例线索。"},
        assigned_command={"task": "先拆解问题再分发专家调查", "focus": "接口、数据库、日志三线并行"},
    )

    summary = focused["coordination_summary"]
    assert summary["dominant_pattern"] in {"multi_signal_incident", "generic_investigation"}
    assert len(summary["priority_tracks"]) >= 2
    assert len(summary["dispatch_targets"]) >= 3
    assert len(summary["evidence_points"]) >= 2


def test_build_judge_focused_context_includes_verdict_summary():
    """验证 JudgeAgent focused context 会输出裁决摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="JudgeAgent",
        compact_context={
            "incident_summary": {
                "title": "/api/v1/orders 接口 502 + CPU 飙高",
                "description": "订单接口 502，数据库连接池 pending 高，CPU 持续飙升",
                "severity": "high",
                "service_name": "order-service",
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "database_tables": ["public.t_order"],
                "error_keywords": ["502", "timeout", "db lock"],
            },
        },
        incident_context={"description": "/orders 502 cpu high db lock"},
        tool_context={"name": "rule_suggestion_bundle", "status": "ok", "summary": "专家证据已汇总。"},
        assigned_command={"task": "裁决当前根因候选", "focus": "收敛证据并给出最终判断"},
    )

    summary = focused["verdict_summary"]
    assert summary["dominant_pattern"] in {"ready_for_verdict", "needs_more_evidence"}
    assert len(summary["decision_axes"]) >= 2
    assert len(summary["evidence_points"]) >= 2


def test_build_verification_focused_context_includes_verification_summary():
    """验证 VerificationAgent focused context 会输出验证摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="VerificationAgent",
        compact_context={
            "incident_summary": {
                "title": "/api/v1/orders 接口 502 + CPU 飙高",
                "description": "订单接口 502，数据库连接池 pending 高，CPU 持续飙升",
                "severity": "high",
                "service_name": "order-service",
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "database_tables": ["public.t_order"],
                "error_keywords": ["502", "timeout"],
            },
        },
        incident_context={"description": "/orders 502 cpu high"},
        tool_context={"name": "metrics_bundle", "status": "ok", "summary": "指标与日志验证入口已具备。"},
        assigned_command={"task": "验证修复是否生效", "focus": "错误率、延迟、连接池三项回落"},
    )

    summary = focused["verification_summary"]
    assert summary["dominant_pattern"] in {"verification_ready", "verification_generic"}
    assert len(summary["checkpoints"]) >= 2
    assert len(summary["evidence_points"]) >= 2


def test_build_critic_focused_context_includes_critique_summary():
    """验证 CriticAgent focused context 会输出质疑摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="CriticAgent",
        compact_context={
            "incident_summary": {"service_name": "order-service", "title": "/orders 502"},
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "database_tables": ["public.t_order"],
                "error_keywords": ["502", "timeout"],
            },
        },
        incident_context={"description": "/orders 502"},
        tool_context={"name": "metrics_bundle", "status": "ok", "summary": "当前证据集中在日志和数据库。"},
        assigned_command={"task": "质疑现有结论", "focus": "指出证据缺口和替代解释"},
    )

    summary = focused["critique_summary"]
    assert summary["dominant_pattern"] in {"evidence_challenge", "generic_challenge"}
    assert len(summary["challenge_axes"]) >= 2
    assert len(summary["evidence_points"]) >= 2


def test_build_rebuttal_focused_context_includes_rebuttal_summary():
    """验证 RebuttalAgent focused context 会输出反驳摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="RebuttalAgent",
        compact_context={
            "incident_summary": {"service_name": "order-service", "title": "/orders 502"},
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "database_tables": ["public.t_order"],
                "error_keywords": ["502", "timeout", "lock"],
            },
        },
        incident_context={"description": "/orders 502 db lock"},
        tool_context={"name": "log_bundle", "status": "ok", "summary": "日志时间线已补齐。"},
        assigned_command={"task": "反驳质疑并补强结论", "focus": "补充闭环证据"},
    )

    summary = focused["rebuttal_summary"]
    assert summary["dominant_pattern"] in {"evidence_reinforcement", "generic_rebuttal"}
    assert len(summary["reinforcement_axes"]) >= 2
    assert len(summary["evidence_points"]) >= 2


def test_build_rule_suggestion_focused_context_includes_rule_summary():
    """验证 RuleSuggestionAgent focused context 会输出规则建议摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="RuleSuggestionAgent",
        compact_context={
            "incident_summary": {"service_name": "order-service", "title": "/orders 502"},
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "database_tables": ["public.t_order"],
                "error_keywords": ["502", "timeout", "pool"],
            },
        },
        incident_context={"description": "/orders 502 pool high"},
        tool_context={"name": "rule_suggestion_bundle", "status": "ok", "summary": "已命中案例与规则建议。"},
        assigned_command={"task": "给出规则化建议", "focus": "止血、告警与守护策略"},
    )

    summary = focused["rule_summary"]
    assert summary["dominant_pattern"] in {"rule_ready", "generic_rule"}
    assert len(summary["recommendation_axes"]) >= 2
    assert len(summary["evidence_points"]) >= 2


def test_build_database_focused_context_includes_causal_summary():
    """验证 DatabaseAgent focused context 会输出表-SQL-session 的因果摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="DatabaseAgent",
        compact_context={
            "interface_mapping": {"database_tables": ["public.t_order", "public.t_order_item"]},
        },
        incident_context={"description": "/orders 502 with db lock"},
        tool_context={
            "data": {
                "engine": "postgresql",
                "schema": "public",
                "tables": ["t_order", "t_order_item"],
                "slow_sql": [
                    {
                        "query": "UPDATE t_inventory SET available=available-1 WHERE sku_id='SPU-7712'",
                        "mean_exec_time": 30000,
                    }
                ],
                "top_sql": [
                    {
                        "query": "SELECT * FROM t_order WHERE id=$1",
                        "calls": 880,
                    }
                ],
                "session_status": [
                    {
                        "state": "active",
                        "wait_event_type": "Lock",
                        "wait_event": "transactionid",
                        "sessions": 14,
                    }
                ],
                "keyword_hits": [
                    {
                        "query": "UPDATE t_inventory SET available=available-1 WHERE sku_id='SPU-7712'",
                        "mean_exec_time": 30000,
                    }
                ],
            }
        },
        assigned_command={"task": "分析锁等待与连接耗尽", "database_tables": ["public.t_order", "public.t_order_item"]},
    )

    summary = focused["causal_summary"]
    assert summary["dominant_pattern"] in {"lock_contention", "db_pressure"}
    assert "public.t_order" in summary["target_tables"]
    assert len(summary["likely_causes"]) >= 1
    assert len(summary["evidence_points"]) >= 2


def test_build_database_focused_context_includes_execution_and_lock_views():
    """验证 DatabaseAgent focused context 会输出执行计划、锁图和 SQL 聚类。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="DatabaseAgent",
        compact_context={"interface_mapping": {"database_tables": ["public.t_order"]}},
        incident_context={"description": "/orders 502 with db lock"},
        tool_context={
            "data": {
                "execution_plans": [
                    {"operator": "Index Scan", "summary": "Index Scan on t_order using idx_order_status"}
                ],
                "session_status": [
                    {
                        "pid": "101",
                        "blocking_pid": "88",
                        "state": "active",
                        "wait_event_type": "Lock",
                        "wait_event": "transactionid",
                    }
                ],
                "slow_sql": [{"query": "UPDATE public.t_order SET status='OK' WHERE id=$1"}],
                "top_sql": [{"query": "SELECT * FROM public.t_order WHERE id=$1"}],
            }
        },
        assigned_command={"task": "分析数据库执行与锁等待", "database_tables": ["public.t_order"]},
    )

    assert focused["execution_plan_summary"]["available"] is True
    assert focused["execution_plan_summary"]["dominant_operators"] == ["Index Scan"]
    assert focused["lock_wait_graph"]["edges"][0]["to"] == "88"
    assert focused["sql_pattern_clusters"]


def test_build_log_focused_context_includes_causal_timeline():
    """验证 LogAgent focused context 会输出首错到用户故障的时间线归因链。"""

    service = AgentToolContextService()
    excerpt = "\n".join(
        [
            "2026-02-20T14:01:07.911+08:00 INFO gateway TraceIdFilter traceId=trc-1 uri=POST /api/v1/orders",
            "2026-02-20T14:01:38.089+08:00 ERROR order-service OrderAppService createOrder failed, error=CannotCreateTransactionException, costMs=30058",
            "2026-02-20T14:01:38.095+08:00 ERROR order-service HikariPool-1 - Connection is not available, request timed out after 30000ms.",
            "2026-02-20T14:01:38.124+08:00 ERROR gateway ErrorLogFilter upstream timeout, status=502, upstream=order-service:8080, costMs=30211",
        ]
    )

    focused = service.build_focused_context(
        agent_name="LogAgent",
        compact_context={
            "log_excerpt": excerpt,
            "investigation_leads": {
                "service_names": ["order-service"],
                "trace_ids": ["trc-1"],
            },
        },
        incident_context={"description": "/orders 502"},
        tool_context={"data": {"excerpt": excerpt, "keywords": ["orders", "timeout"]}},
        assigned_command={"task": "重建时间线", "focus": "首错与放大链路"},
    )

    timeline = focused["causal_timeline"]
    assert len(timeline) >= 3
    assert timeline[0]["stage"] == "request_entry"
    assert any(item["stage"] == "first_error" for item in timeline)
    assert any(item["stage"] == "resource_exhaustion" for item in timeline)
    assert timeline[-1]["stage"] == "user_visible_failure"


def test_build_log_focused_context_includes_trace_alignment():
    """验证 LogAgent focused context 会输出 trace 对齐和传播链。"""

    service = AgentToolContextService()
    excerpt = "\n".join(
        [
            "2026-02-20T14:01:07.911+08:00 INFO gateway TraceIdFilter traceId=trc-1 uri=POST /api/v1/orders",
            "2026-02-20T14:01:38.095+08:00 ERROR order-service HikariPool-1 - Connection is not available, request timed out after 30000ms.",
            "2026-02-20T14:01:38.124+08:00 ERROR gateway ErrorLogFilter upstream timeout, status=502",
        ]
    )

    focused = service.build_focused_context(
        agent_name="LogAgent",
        compact_context={
            "log_excerpt": excerpt,
            "investigation_leads": {"service_names": ["order-service"], "trace_ids": ["trc-1"]},
        },
        incident_context={"description": "/orders 502"},
        tool_context={
            "data": {
                "excerpt": excerpt,
                "keywords": ["orders", "timeout"],
                "remote_telemetry": {
                    "payload": {
                        "spans": [
                            {"timestamp": "2026-02-20T14:01:20.000+08:00", "service": "order-service", "span": "OrderAppService", "summary": "createOrder span"}
                        ]
                    }
                },
                "remote_prometheus": {
                    "payload": {
                        "signals": [
                            {"timestamp": "2026-02-20T14:01:30.000+08:00", "metric": "db.pool.pending", "summary": "pending threads high"}
                        ]
                    }
                },
            }
        },
        assigned_command={"task": "做统一时序对齐", "focus": "trace 与 metric 放大链"},
    )

    assert focused["trace_timeline"]
    assert any(item["source"] == "trace" for item in focused["trace_timeline"])
    assert any(item["source"] == "metric" for item in focused["trace_timeline"])
    assert any(item["stage"] == "resource_contention" for item in focused["propagation_chain"])


def test_build_metrics_focused_context_includes_causal_metric_chain():
    """验证 MetricsAgent focused context 会输出指标时序因果链。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="MetricsAgent",
        compact_context={
            "incident_summary": {"service_name": "order-service"},
        },
        incident_context={"description": "/orders 502 cpu 380% db_conn 100/100"},
        tool_context={
            "data": {
                "signals": [
                    {"metric": "cpu", "label": "CPU", "value": "380%", "snippet": "order-service CPU: 320%~380%"},
                    {"metric": "threads", "label": "线程", "value": "920", "snippet": "JVM 活跃线程: 920"},
                    {"metric": "db_conn", "label": "DB连接", "value": "100/100", "snippet": "DB 活跃连接: 100/100（打满）"},
                    {"metric": "error_rate", "label": "错误率", "value": "37%", "snippet": "网关 /api/v1/orders 5xx: 37%"},
                ],
                "remote_telemetry": {"enabled": True, "status": "ok", "payload": {"window": "5m"}},
                "remote_prometheus": {"enabled": True, "status": "ok", "payload": {"queries": 3}},
            }
        },
        assigned_command={"task": "分析指标异常链路", "focus": "前置指标与用户故障指标"},
    )

    chain = focused["causal_metric_chain"]
    assert len(chain) >= 3
    assert any(item["stage"] == "resource_pressure" for item in chain)
    assert any(item["stage"] == "capacity_saturation" for item in chain)
    assert chain[-1]["stage"] == "user_visible_failure"


def test_build_impact_focused_context_includes_function_interface_and_user_scope():
    """验证 ImpactAnalysisAgent focused context 会输出功能、接口和用户影响估算摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="ImpactAnalysisAgent",
        compact_context={
            "incident_summary": {
                "title": "/api/v1/orders 下单接口 502",
                "description": "订单创建接口持续 502，影响下单流程",
                "severity": "high",
            },
            "interface_mapping": {
                "feature": "订单创建",
                "domain": "交易域",
                "aggregate": "订单聚合",
                "owner_team": "order-domain-team",
                "owner": "alice",
                "endpoint": {
                    "method": "POST",
                    "path": "/api/v1/orders",
                    "service": "order-service",
                },
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "dependency_services": ["gateway-service"],
                "error_keywords": ["502", "timeout"],
                "monitor_items": ["gateway.orders.5xx"],
            },
        },
        incident_context={"description": "下单接口 502，用户创建订单失败"},
        tool_context={
            "data": {
                "estimated_users": 1200,
                "affected_ratio": "约 18%",
                "estimation_basis": "根据故障窗口内下单入口失败率和接口流量估算",
                "confidence": 0.64,
            }
        },
        assigned_command={"task": "分析问题影响范围", "focus": "功能、接口和用户影响"},
    )

    assert focused["impact_problem_frame"]["service"] == "order-service"
    assert focused["affected_functions"]
    assert focused["affected_functions"][0]["name"] == "订单创建"
    assert focused["affected_interfaces"][0]["endpoint"] == "/api/v1/orders"
    assert focused["affected_user_scope"]["estimated_users"] == 1200
    assert focused["affected_user_scope"]["confidence"] >= 0.6


def test_build_change_focused_context_includes_causal_summary():
    """验证 ChangeAgent focused context 会输出变更因果摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="ChangeAgent",
        compact_context={
            "interface_mapping": {
                "endpoint": {
                    "method": "POST",
                    "path": "/api/v1/orders",
                    "service": "order-service",
                },
                "code_artifacts": ["src/order/OrderController.java", "src/order/OrderService.java"],
            },
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
                "code_artifacts": ["src/order/OrderController.java", "src/order/OrderService.java"],
            },
        },
        incident_context={"description": "/orders 502 after release"},
        tool_context={
            "data": {
                "changes": [
                    {
                        "commit": "a1b2c3d4e5f6",
                        "time": "2026-03-09 10:15:00 +0800",
                        "author": "alice",
                        "subject": "order-service: adjust OrderController route and add retry around createOrder",
                    },
                    {
                        "commit": "b2c3d4e5f6a7",
                        "time": "2026-03-09 10:22:00 +0800",
                        "author": "bob",
                        "subject": "inventory client timeout threshold updated for order flow",
                    },
                ]
            }
        },
        assigned_command={"task": "分析近期变更风险", "focus": "接口路由与重试逻辑"},
    )

    summary = focused["causal_summary"]
    assert summary["dominant_pattern"] in {"recent_release_regression", "change_window_noise"}
    assert any(item.get("commit") == "a1b2c3d4e5f6" for item in summary["suspect_changes"])
    assert len(summary["mechanism_links"]) >= 1
    assert len(summary["evidence_points"]) >= 2


def test_build_runbook_focused_context_includes_action_summary():
    """验证 RunbookAgent focused context 会输出处置与验证摘要。"""

    service = AgentToolContextService()
    focused = service.build_focused_context(
        agent_name="RunbookAgent",
        compact_context={
            "incident_summary": {"service_name": "order-service"},
            "investigation_leads": {
                "api_endpoints": ["POST /api/v1/orders"],
                "service_names": ["order-service"],
            },
        },
        incident_context={"description": "/orders 502 with db lock"},
        tool_context={
            "data": {
                "source": "knowledge_base",
                "items": [
                    {
                        "title": "订单服务 502 连接池耗尽处置手册",
                        "entry_type": "runbook",
                        "runbook_fields": {
                            "steps": [
                                "检查 Hikari pending threads 与 active 连接数",
                                "查看 pg_stat_activity 中锁等待会话",
                                "必要时限制重试流量并扩容连接池",
                            ],
                            "verification_steps": [
                                "确认 /api/v1/orders 5xx 回落",
                                "确认数据库连接池 pending 降到 0",
                            ],
                        },
                    },
                    {
                        "title": "订单创建锁等待复盘案例",
                        "entry_type": "case",
                        "summary": "库存扣减 SQL 锁等待导致事务堆积，最终引发连接池耗尽。",
                    },
                ],
            }
        },
        assigned_command={"task": "给出处置建议", "focus": "止血动作与验证步骤"},
    )

    summary = focused["action_summary"]
    assert summary["dominant_pattern"] in {"matched_runbook", "knowledge_gap"}
    assert len(summary["recommended_steps"]) >= 2
    assert len(summary["verification_steps"]) >= 1
    assert len(summary["evidence_points"]) >= 1


def test_collect_metrics_signals_preserves_db_connection_ratio():
    """验证指标提取会保留数据库连接比值。"""

    service = AgentToolContextService()

    signals = service._collect_metrics_signals(  # noqa: SLF001 - validating metric parsing logic
        {"log_excerpt": "order.error.rate=18.7% hikari_pending=87 db_conn=20/20"},
        {},
    )

    db_signal = next(item for item in signals if item.get("metric") == "db_conn")
    assert db_signal["value"] == "20/20"


@pytest.mark.asyncio
async def test_database_agent_context_reads_sqlite_snapshot(tmp_path, monkeypatch):
    """验证databaseAgent上下文读取SQLite快照。"""
    
    db_path = tmp_path / "ops_snapshot.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE t_order (id INTEGER PRIMARY KEY, sku_id TEXT, status TEXT)")
        cur.execute("CREATE INDEX idx_order_sku ON t_order(sku_id)")
        cur.execute("CREATE TABLE slow_sql (sql_text TEXT, duration_ms INTEGER)")
        cur.execute("INSERT INTO slow_sql(sql_text, duration_ms) VALUES (?, ?)", ("SELECT * FROM t_order", 30123))
        cur.execute("CREATE TABLE top_sql (sql_text TEXT, exec_count INTEGER)")
        cur.execute("INSERT INTO top_sql(sql_text, exec_count) VALUES (?, ?)", ("SELECT id FROM t_order", 889))
        cur.execute("CREATE TABLE session_status (active_sessions INTEGER, running INTEGER)")
        cur.execute("INSERT INTO session_status(active_sessions, running) VALUES (?, ?)", (112, 45))
        conn.commit()
    finally:
        conn.close()

    async def _fake_get_config():
        """为测试场景提供get配置模拟实现。"""
        return AgentToolingConfig(
            database=DatabaseToolConfig(enabled=True, db_path=str(db_path), max_rows=10),
        )

    monkeypatch.setattr("app.services.agent_tool_context_service.tooling_service.get_config", _fake_get_config)

    service = AgentToolContextService()
    payload = await service.build_context(
        agent_name="DatabaseAgent",
        compact_context={"log_excerpt": "orders timeout"},
        incident_context={"description": "/orders 502 with db lock"},
        assigned_command={
            "task": "读取数据库慢sql和索引",
            "focus": "slow sql + index",
            "database_tables": ["t_order"],
            "use_tool": True,
        },
    )

    assert payload["name"] == "db_snapshot_reader"
    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert int(payload["data"]["table_count"]) == 1
    assert payload["data"]["tables"] == ["t_order"]
    assert payload["data"]["requested_tables"] == ["t_order"]
    assert len(payload["data"]["slow_sql"]) == 1
    assert len(payload["data"]["top_sql"]) == 1
    assert len(payload["data"]["session_status"]) == 1
    assert any(
        str(item.get("action") or "") == "sqlite_query" and str(item.get("status") or "") == "ok"
        for item in list(payload.get("audit_log") or [])
    )


@pytest.mark.asyncio
async def test_database_agent_context_reads_postgres_snapshot(monkeypatch):
    """验证databaseAgent上下文读取Postgres快照。"""
    
    class _FakeConn:
        """为测试场景提供FakeConn辅助对象。"""
        async def fetch(self, sql, *args):  # noqa: ANN001, ANN002
            """为测试场景提供fetch辅助逻辑。"""
            text = str(sql)
            if "information_schema.tables" in text:
                return [{"table_name": "t_order"}, {"table_name": "t_order_item"}]
            if "information_schema.columns" in text:
                table = str(args[1] if len(args) > 1 else "")
                if table == "t_order":
                    return [
                        {"column_name": "id", "data_type": "bigint", "is_nullable": "NO", "column_default": None, "ordinal_position": 1},
                        {"column_name": "status", "data_type": "varchar", "is_nullable": "YES", "column_default": None, "ordinal_position": 2},
                    ]
                return [
                    {"column_name": "order_id", "data_type": "bigint", "is_nullable": "NO", "column_default": None, "ordinal_position": 1},
                    {"column_name": "sku_id", "data_type": "varchar", "is_nullable": "YES", "column_default": None, "ordinal_position": 2},
                ]
            if "FROM pg_indexes" in text:
                return [{"indexname": "idx_order_status", "indexdef": "CREATE INDEX idx_order_status ON t_order(status)"}]
            if "pg_stat_statements" in text and "total_exec_time" in text:
                return [{"query": "select * from t_order", "calls": 101, "total_exec_time": 2200.0, "mean_exec_time": 21.8, "rows": 99}]
            if "pg_stat_statements" in text and "ORDER BY calls" in text:
                return [{"query": "select id from t_order", "calls": 880, "total_exec_time": 850.0, "mean_exec_time": 1.0, "rows": 880}]
            if "FROM pg_stat_activity" in text:
                return [{"state": "active", "wait_event_type": "Lock", "wait_event": "transactionid", "sessions": 14}]
            return []

        async def close(self):
            """为测试场景提供关闭辅助逻辑。"""
            return None

    class _FakeAsyncpg:
        """为测试场景提供FakeAsyncpg辅助对象。"""

        @staticmethod
        async def connect(**kwargs):  # noqa: ANN003
            """为测试场景提供connect辅助逻辑。"""
            assert "dsn" in kwargs
            return _FakeConn()

    async def _fake_get_config():
        """为测试场景提供get配置模拟实现。"""
        return AgentToolingConfig(
            database=DatabaseToolConfig(
                enabled=True,
                engine="postgresql",
                postgres_dsn="postgresql://user:pwd@localhost:5432/order_db",
                pg_schema="public",
                max_rows=10,
                connect_timeout_seconds=5,
            ),
        )

    monkeypatch.setattr("app.services.agent_tool_context_service.asyncpg", _FakeAsyncpg())
    monkeypatch.setattr("app.services.agent_tool_context_service.tooling_service.get_config", _fake_get_config)

    service = AgentToolContextService()
    payload = await service.build_context(
        agent_name="DatabaseAgent",
        compact_context={"log_excerpt": "orders timeout"},
        incident_context={"description": "/orders 502 with db lock"},
        assigned_command={
            "task": "分析postgres慢sql和session",
            "focus": "slow sql + session",
            "database_tables": ["public.t_order"],
            "use_tool": True,
        },
    )

    assert payload["name"] == "db_snapshot_reader"
    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert payload["data"]["engine"] == "postgresql"
    assert int(payload["data"]["table_count"]) == 1
    assert payload["data"]["tables"] == ["t_order"]
    assert payload["data"]["requested_tables"] == ["public.t_order"]
    assert len(payload["data"]["slow_sql"]) == 1
    assert len(payload["data"]["top_sql"]) == 1
    assert len(payload["data"]["session_status"]) == 1
    assert any(
        str(item.get("action") or "") == "postgres_query" and str(item.get("status") or "") == "ok"
        for item in list(payload.get("audit_log") or [])
    )


@pytest.mark.asyncio
async def test_runbook_agent_context_prefers_knowledge_base(monkeypatch):
    """验证 RunbookAgent 优先命中新知识库。"""

    async def _fake_search_reference_entries(*, query, limit=5, entry_types=None):  # noqa: ANN001
        return [
            {
                "id": "kb_runbook_1",
                "entry_type": "runbook",
                "title": "订单 5xx 排查 SOP",
                "summary": "优先检查网关、下游和数据库。",
                "content": "SOP 正文",
                "tags": ["orders", "5xx"],
                "service_names": ["order-service"],
                "domain": "order",
                "aggregate": "OrderAggregate",
                "updated_at": "2026-03-09T08:00:00Z",
                "runbook_fields": {
                    "steps": ["检查网关日志", "检查 DB 连接池"],
                    "verification_steps": ["确认 5xx 回落"],
                },
            }
        ]

    async def _fake_execute(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("knowledge base hit should skip legacy case library fallback")

    monkeypatch.setattr(
        "app.services.agent_tool_context_service.knowledge_service.search_reference_entries",
        _fake_search_reference_entries,
    )

    service = AgentToolContextService()
    monkeypatch.setattr(service._case_library, "execute", _fake_execute)  # noqa: SLF001

    payload = await service.build_context(
        agent_name="RunbookAgent",
        compact_context={"log_excerpt": "orders 502 hikari pending"},
        incident_context={"description": "/orders 502"},
        assigned_command={
            "task": "检索相似案例和 SOP",
            "focus": "runbook",
            "use_tool": True,
        },
    )

    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert len(list(payload["data"].get("items") or [])) == 1
    assert payload["data"]["source"] == "knowledge_base"
    assert any(
        str(item.get("action") or "") == "knowledge_search" and str(item.get("status") or "") == "ok"
        for item in list(payload.get("audit_log") or [])
    )


@pytest.mark.asyncio
async def test_runbook_agent_context_falls_back_to_legacy_case_library(monkeypatch):
    """验证新知识库未命中时回退旧案例库。"""

    async def _fake_search_reference_entries(*, query, limit=5, entry_types=None):  # noqa: ANN001
        return []

    class _LegacyResult:
        success = True
        error = None
        data = {"items": [{"id": "case_1", "title": "旧案例", "solution": "回退方案"}]}

    async def _fake_execute(*args, **kwargs):  # noqa: ANN002, ANN003
        return _LegacyResult()

    monkeypatch.setattr(
        "app.services.agent_tool_context_service.knowledge_service.search_reference_entries",
        _fake_search_reference_entries,
    )

    service = AgentToolContextService()
    monkeypatch.setattr(service._case_library, "execute", _fake_execute)  # noqa: SLF001

    payload = await service.build_context(
        agent_name="RunbookAgent",
        compact_context={"log_excerpt": "inventory timeout"},
        incident_context={"description": "/orders 502"},
        assigned_command={
            "task": "检索相似案例和 SOP",
            "focus": "runbook",
            "use_tool": True,
        },
    )

    assert payload["used"] is True
    assert payload["status"] == "ok"
    assert payload["data"]["source"] == "legacy_case_library"
    assert any(
        str(item.get("action") or "") == "knowledge_search" and str(item.get("status") or "") == "unavailable"
        for item in list(payload.get("audit_log") or [])
    )


@pytest.mark.asyncio
async def test_build_context_runs_plugin_tool_from_skill_metadata(tmp_path, monkeypatch):
    """验证 skill metadata.required_tools 可触发插件 tool 执行并回填上下文。"""

    skill_dir = tmp_path / "skills" / "design-consistency-check"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: design-consistency-check\n"
            "description: 设计一致性检查\n"
            "triggers: design,api\n"
            "agents: LogAgent\n"
            "---\n"
            "body"
        ),
        encoding="utf-8",
    )
    (skill_dir / "metadata.json").write_text(
        (
            "{\n"
            "  \"skill_id\": \"design-consistency-check\",\n"
            "  \"name\": \"设计一致性检查\",\n"
            "  \"applicable_experts\": [\"LogAgent\"],\n"
            "  \"required_tools\": [\"design_spec_alignment\"]\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    plugin_dir = tmp_path / "tools" / "design_spec_alignment"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "tool.json").write_text(
        (
            "{\n"
            "  \"tool_id\": \"design_spec_alignment\",\n"
            "  \"name\": \"设计一致性插件\",\n"
            "  \"runtime\": \"python\",\n"
            "  \"entry\": \"run.py\",\n"
            "  \"timeout_seconds\": 5,\n"
            "  \"allowed_agents\": [\"LogAgent\"]\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    (plugin_dir / "run.py").write_text(
        (
            "import json, sys\n"
            "payload = json.loads(sys.stdin.read() or '{}')\n"
            "print(json.dumps({'success': True, 'summary': 'plugin ok', 'seen_agent': payload.get('agent_name')}, ensure_ascii=False))\n"
        ),
        encoding="utf-8",
    )

    async def _fake_get_config():
        return AgentToolingConfig(
            skills=AgentSkillConfig(enabled=True, skills_dir=str(tmp_path / "skills"), max_skills=2),
            tool_plugins=AgentToolPluginConfig(enabled=True, plugins_dir=str(tmp_path / "tools"), max_calls=2),
        )

    monkeypatch.setattr("app.services.agent_tool_context_service.tooling_service.get_config", _fake_get_config)

    service = AgentToolContextService()
    payload = await service.build_context(
        agent_name="LogAgent",
        compact_context={"incident_title": "orders 502"},
        incident_context={"description": "gateway 502"},
        assigned_command={"task": "请按设计一致性检查", "skill_hints": ["design-consistency-check"], "use_tool": True},
    )

    plugin_outputs = list((payload.get("data") or {}).get("plugin_tool_outputs") or [])
    assert plugin_outputs
    assert plugin_outputs[0]["tool_name"] == "design_spec_alignment"
    assert plugin_outputs[0]["success"] is True
    assert plugin_outputs[0]["seen_agent"] == "LogAgent"
    assert any(
        str(item.get("action") or "") == "plugin_tool_call" and str(item.get("status") or "") == "ok"
        for item in list(payload.get("audit_log") or [])
    )
