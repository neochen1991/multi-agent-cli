---
name: order-timeout-rca
description: 订单链路超时故障排查技能包（本地资源优先，可插拔外部资源）
---

# Order Timeout RCA Skill

## 适用场景
- `/orders` 接口 5xx / timeout
- 网关超时 + 连接池打满 + DB 锁等待

## 输入契约
- `interface_url`
- `log_excerpt`
- `stacktrace`
- `metrics_snapshot`

## 输出契约
- `root_cause_candidates` (Top-K)
- `evidence_refs`
- `verification_plan`
- `rollback_plan`

## 禁用项
- 不允许直接执行生产变更
- 无审批信息时只能给出建议，不可执行动作
