---
name: change-correlation-review
description: 变更关联评估技能，识别故障窗口内可疑发布与提交
triggers: 发布,变更,commit,deploy,rollback,配置变更,feature flag
agents: ChangeAgent,CodeAgent
---

## Goal
- 用“时间相关 + 机制相关”筛选可疑变更 Top-K。

## Playbook
1. 拉取故障窗口前后变更清单（代码/配置/依赖/开关）。
2. 逐项评估触发机制与影响范围。
3. 给候选排序与回滚优先级。
4. 为每个候选给反证条件，避免误报。

## Output Contract
- `analysis`: 变更关联解释。
- `conclusion`: Top-K 可疑变更与建议动作。
- `evidence_chain`: 提交/发布记录证据。
