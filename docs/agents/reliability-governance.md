# Reliability And Governance

本文档补充多 Agent 运行时的可靠性与治理约束，作为 `/Users/neochen/multi-agent-cli_v2/AGENTS.md` 的展开说明。

## 1. 可靠性目标

- 任意会话都必须可终止，不能长期停在 `pending / running`。
- 关键 Agent 降级时，系统必须显式记录 `degraded / missing / context_grounded_without_tool`。
- runtime、result、report 三层的 `confidence` 口径必须一致可解释。

## 2. 运行时治理信号

- `evidence_coverage`
- `debate_stability_score`
- `top_k_hypotheses`
- `claim_graph`

这些信号同时服务于：
- 路由收口
- benchmark richer scoring
- governance baseline 趋势
- team 维度治理指标

## 3. 当前落地点

- benchmark 评分：`/Users/neochen/multi-agent-cli_v2/backend/app/benchmark/scoring.py`
- 治理聚合：`/Users/neochen/multi-agent-cli_v2/backend/app/services/governance_ops_service.py`
- 运行时收口：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`

## 4. Claim Graph 质量门

最小 `claim_graph` 当前要求包含：
- `primary_claim`
- `supports`
- `contradicts`
- `missing_checks`
- `eliminated_alternatives`

其中：
- `supports` 用于判断是否有支持证据
- `eliminated_alternatives` 用于判断是否排除了高频错误候选
- `missing_checks` 用于判断是否显式说明了待验证项
