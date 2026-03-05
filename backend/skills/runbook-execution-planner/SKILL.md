---
name: runbook-execution-planner
description: 处置手册执行规划技能，输出可执行止血与恢复步骤
triggers: runbook,sop,处置,止血,恢复,回滚,操作手册
agents: RunbookAgent,ProblemAnalysisAgent
---

## Goal
- 把案例经验转为当前事故可执行行动清单。

## Playbook
1. 匹配最相似历史案例，指出差异。
2. 先输出 P0 止血动作（5~15 分钟可执行）。
3. 再输出 P1 恢复动作与 P2 治理动作。
4. 每步附验证点、风险与回滚条件。

## Safety Gate
- 高风险动作默认需人工确认。
- 无验证点的动作不得入列。

## Output Contract
- `analysis`: 方案选择依据。
- `conclusion`: 执行序列与优先级。
- `evidence_chain`: 案例引用与适配说明。
