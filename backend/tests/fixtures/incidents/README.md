# Incident Fixtures

每个 `*.json` 文件是一条可回放的生产故障样本，字段：
- `id`
- `title`
- `symptom`
- `log_excerpt`
- `stacktrace`
- `expected_root_cause`
- `expected_domain`
- `expected_aggregate`

用于：`scripts/smoke-e2e.mjs` 多场景回归与本地人工复盘。

可选扩展字段：
- `scenario`
- `owner`
- `tags`
- `golden`
- `expected_causal_chain`
- `must_include`
- `must_exclude`
- `distractor_root_causes`

说明：
- benchmark loader 现在也会消费：
  - `expected_causal_chain`
  - `must_include`
  - `must_exclude`
- 这些字段当前用于 `claim_graph` richer scoring：
  - `must_include` 对应 `supports`
  - `must_exclude` 对应 `eliminated_alternatives`
  - `expected_causal_chain` 会影响 `missing_checks` 的期望分
