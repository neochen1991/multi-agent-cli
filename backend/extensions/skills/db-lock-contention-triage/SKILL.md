---
name: db-lock-contention-triage
description: 数据库锁争用快速分诊技能
triggers: deadlock,lock wait timeout,for update,row lock,数据库锁,死锁
agents: DatabaseAgent,LogAgent,DomainAgent,JudgeAgent
---

## Goal

在数据库性能或可用性故障中，快速区分“锁争用根因”与“业务慢查询症状”。

## Checklist

1. 抽取锁等待/死锁信号，确认是否存在持续性阻塞。
2. 识别热点表和潜在阻塞会话，标注高风险写入链路。
3. 输出“立刻止血”与“根因修复”两层建议，避免只给方向不落地。

## Output Contract

- `lock_root_hypothesis`: 锁争用根因假设
- `hot_tables`: 高风险表
- `blocker_candidates`: 阻塞方候选
- `mitigation_steps`: 止血与修复建议
