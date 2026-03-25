---
name: release-regression-correlation
description: 发布回归时序关联分析技能
triggers: release,deploy,rollback,commit,version,上线,回滚,发布
agents: ChangeAgent,CodeAgent,DomainAgent,JudgeAgent
---

## Goal

在“疑似发布引发故障”场景中，基于时间线与证据链给出可解释结论，减少拍脑袋归因。

## Checklist

1. 对齐发布/回滚时间点与故障爆发时间点，标注前后关系。
2. 核对版本、提交、构建号等标识，形成可追溯证据链。
3. 同时列出非发布线索，避免单一证据造成误判。

## Output Contract

- `release_correlation`: `high | medium | low`
- `release_evidence`: 发布相关证据
- `counter_evidence`: 反证据（非发布线索）
- `verification_actions`: 建议验证动作
