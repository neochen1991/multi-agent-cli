---
name: metrics-anomaly-triage
description: 指标异常分诊技能，定位异常窗口与前后置指标关系
triggers: 指标,cpu,线程,连接池,错误率,延迟,p99,prometheus,grafana,slo
agents: MetricsAgent,VerificationAgent
---

## Goal
- 从时序关系定位“先因后果”，而非只看峰值。

## Playbook
1. 定义窗口：开始、峰值、恢复。
2. 基线对比：故障前 15~30 分钟 vs 故障期。
3. 标注链路：前置指标（资源/队列）-> 后置指标（5xx/超时）。
4. 给阈值和告警建议，支持后续验证。

## Evidence Standard
- 至少 3 个关键指标，且包含先后关系。
- 缺失监控项要显式列出并给补采建议。

## Output Contract
- `analysis`: 时序异常链路。
- `conclusion`: 指标侧主判断。
- `evidence_chain`: 指标值、窗口、趋势证据。
