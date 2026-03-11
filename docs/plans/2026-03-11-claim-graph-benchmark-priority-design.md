# Claim Graph Benchmark Priority Design

日期：2026-03-11

## 背景

当前 runtime 已经在 `final_judgment` 下补出了最小 `claim_graph`：

- `primary_claim`
- `supports`
- `contradicts`
- `missing_checks`
- `eliminated_alternatives`

但 benchmark 评分链路仍停留在非常轻的文本重叠：

- `expected_root_cause` vs `predicted_root_cause`
- `predicted_candidates`
- `evidence_source_count`

这会带来两个问题：

1. 系统即使“主因说对，但没有排除错误候选，也没有补待验证项”，benchmark 仍可能给较高分。
2. fixture 已经有 `must_include / must_exclude / expected_causal_chain` 等 richer 字段，但当前完全未参与自动评分。

## 目标

在不改运行时策略的前提下，把 benchmark 升级成可以消费 `claim_graph` 的第一版质量门。

本轮只做三类结构化判定：

1. `supports`：是否有足够的支持证据
2. `eliminated_alternatives`：是否明确排除了 fixture 里的错误候选
3. `missing_checks`：是否识别出仍需验证的关键检查项

## 不做的事

- 不修改 runtime 收口逻辑
- 不修改 governance UI
- 不引入复杂 NLP 或 embedding 打分
- 不要求所有 fixture 都必须补齐 richer 字段

## 方案比较

### 方案 A：只改 aggregate summary

只在 benchmark 报表汇总里新增统计字段，不改单 case 评分。

优点：
- 改动最小

缺点：
- 无法形成真正 case-level 质量门
- CI 很难基于它做 gate

### 方案 B：推荐，单 case + summary 一起升级

在 `evaluate_case()` 中新增 claim-graph 评分，再在 `aggregate_cases()` 汇总这些分值。

优点：
- case 级和 summary 级都能看
- 改动面仍然很小
- 便于后续治理侧直接复用 benchmark 输出

缺点：
- 需要让 fixture loader 读取更多扩展字段

### 方案 C：直接把 governance 一起接上

同时改 benchmark 与治理统计。

优点：
- 一次性打通

缺点：
- 改动面偏大
- 不利于隔离验证

## 推荐方案

采用方案 B。

## 具体设计

### 1. Fixture Loader 扩展

`IncidentFixture` 新增可选字段：

- `expected_causal_chain: List[str]`
- `must_include: List[str]`
- `must_exclude: List[str]`

这些字段都允许为空，保证旧 fixture 不会失效。

### 2. Case 级评分扩展

在 `evaluate_case()` 里新增输入：

- `claim_graph`
- `expected_causal_chain`
- `must_include`
- `must_exclude`

新增输出：

- `claim_graph_support_score`
- `claim_graph_exclusion_score`
- `claim_graph_missing_check_score`
- `claim_graph_quality_score`

判定规则保持朴素：

- `support_score`
  - 如果 fixture 给了 `must_include`，则检查 `supports` 中命中率
  - 否则按 `supports` 数量给基础分

- `exclusion_score`
  - 如果 fixture 给了 `must_exclude`，则检查 `eliminated_alternatives` 是否命中
  - 未提供 `must_exclude` 时，不把它计入惩罚

- `missing_check_score`
  - 如果 fixture 给了 `expected_causal_chain` 或 `must_include`，并且结论不是满证据场景，则检查 `missing_checks` 是否非空
  - 没有 richer 字段时给中性分，不惩罚旧 case

最终：

- `claim_graph_quality_score`
  - 使用加权平均
  - 推荐权重：`supports 0.5 / exclusion 0.3 / missing_checks 0.2`

### 3. Summary 汇总扩展

`aggregate_cases()` 新增：

- `avg_claim_graph_quality_score`
- `claim_graph_support_rate`
- `claim_graph_exclusion_rate`
- `claim_graph_missing_check_rate`

### 4. Runner 输出扩展

`BenchmarkRunner._run_one()` 需把 `result.claim_graph` 传进 `evaluate_case()`。

## 验证策略

新增测试覆盖：

1. fixture loader 能读取 richer 字段
2. scoring 能根据 `claim_graph` 和 fixture 扩展字段打分
3. aggregate summary 能正确汇总 claim-graph 质量指标

## 风险

最大风险是“旧 fixture 没 richer 字段时被误降分”。  
规避方式是：所有新增字段都按可选处理，缺失时给中性分或跳过，不影响现有基线。
