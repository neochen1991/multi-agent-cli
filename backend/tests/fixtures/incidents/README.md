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
