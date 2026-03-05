---
name: evidence-rebuttal
description: 证据反驳技能，逐条回应质疑并收敛执行建议
triggers: 反驳,回应,采纳,补证,收敛,rebuttal
agents: RebuttalAgent
---

## Goal
- 把“争论”转成“可验证收敛”。

## Playbook
1. 对每条质疑标注：采纳/部分采纳/驳回。
2. 每条回应附证据或补证计划。
3. 若修正结论，明确前后差异与影响。
4. 给下一步最小执行动作。

## Output Contract
- `analysis`: 逐条回应摘要。
- `conclusion`: 更新后的收敛结论。
- `evidence_chain`: 响应证据。
