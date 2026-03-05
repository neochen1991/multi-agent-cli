---
name: verification-plan-builder
description: 验证计划构建技能，覆盖功能/性能/回归/回滚闭环
triggers: 验证,回归,回滚,压测,验收,slo,verification
agents: VerificationAgent,JudgeAgent
---

## Goal
- 为修复提供可执行、可度量、可回退的验证方案。

## Playbook
1. 功能验证：关键路径与失败场景。
2. 性能验证：延迟、吞吐、资源占用、SLO。
3. 回归验证：相关接口与依赖链路。
4. 回滚验证：触发阈值、自动化回退动作。

## Output Contract
- `analysis`: 验证策略说明。
- `verification_plan`: 分维度步骤、通过标准、负责人。
- `conclusion`: 发布门禁建议（通过/观察/阻断）。
