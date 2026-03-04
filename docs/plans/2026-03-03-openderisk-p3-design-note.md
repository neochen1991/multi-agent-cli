# P3 Design Note - Governance & Benchmark

## Scope
- Benchmark 指标升级：Top3、跨源证据率、分场景空结论率
- 治理指标升级：token 趋势、超时热点、工具失败 TopN、SLA
- 外部协同升级：字段映射模板与自动同步开关

## Implementation
- `benchmark/runner+scoring` 扩展统计维度，gate 增加阈值。
- `governance_ops_service` 聚合趋势/热点/SLA 并由治理中心展示。
- 外部协同新增模板查询和 settings 配置接口。

## Verification
- 后端 `python3 -m compileall -q app`
- 前端 `npm run typecheck && npm run build`
