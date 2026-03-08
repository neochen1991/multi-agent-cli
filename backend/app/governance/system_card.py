"""System card for governance center."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from app.config import settings


def build_system_card() -> Dict[str, Any]:
    """构建构建系统卡片，供后续节点或调用方直接使用。"""
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "system": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "llm_model": settings.llm_model,
            "llm_base_url": settings.LLM_BASE_URL,
            "max_rounds": settings.DEBATE_MAX_ROUNDS,
            "consensus_threshold": settings.DEBATE_CONSENSUS_THRESHOLD,
        },
        "boundaries": [
            "不直接执行生产变更命令",
            "不自动回滚线上服务，仅输出建议",
            "无外部数据库依赖（本地文件/内存）",
        ],
        "disabled_scenarios": [
            "未审批的高风险修复动作禁止自动执行",
            "缺失跨源证据的结论禁止自动出报告",
            "无法获取核心日志/指标时禁止给出高置信修复指令",
        ],
        "safety_controls": [
            "工具调用开关按 Agent 可配置",
            "会话谱系全量记录",
            "失败会话支持回放",
            "无有效大模型结论时禁止生成报告",
            "No-Regression Gate 不通过时阻断执行",
        ],
        "audit": {
            "lineage_store": "local_store/lineage/*.jsonl",
            "tool_audit_api": "/api/v1/settings/tooling/audit/{session_id}",
            "remediation_audit_store": "local_store/remediation_actions.json",
        },
        "known_limits": [
            "结果依赖输入日志和工具可用性",
            "长会话在高延迟模型下仍可能耗时较长",
            "跨系统根因需更多外部遥测接入",
        ],
    }


def estimate_cost(case_count: int, avg_tokens: int = 3500) -> Dict[str, Any]:
    # 占位估算：用于治理页趋势展示（不绑定特定供应商计费）
    """计算estimatecost，为治理、裁决或展示提供量化依据。"""
    total_tokens = max(0, int(case_count or 0)) * max(0, int(avg_tokens or 0))
    return {
        "cases": max(0, int(case_count or 0)),
        "estimated_tokens": total_tokens,
        "note": "为粗略估算，仅用于趋势治理。",
    }
