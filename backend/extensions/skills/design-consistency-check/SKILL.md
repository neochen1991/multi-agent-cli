---
name: design-consistency-check
description: 设计一致性检查技能
triggers: design,spec,api,contract,workflow
agents: CodeAgent,DomainAgent,LogAgent,JudgeAgent
---

## Goal

在已有日志/代码/责任田证据基础上，额外检查实现行为是否偏离设计预期。

## Checklist

1. 抽取本轮与接口行为相关的设计候选点。
2. 对照当前实现证据，标记已匹配点与缺失点。
3. 若证据不足，明确写出“不足项”和下一步补证建议。

## Output Contract

- `design_alignment_status`: `aligned | partially_aligned | misaligned | insufficient_context`
- `matched_design_points`: 设计与实现一致点
- `missing_design_points`: 设计要求但当前证据未覆盖点
- `conflicts`: 设计与实现冲突点
