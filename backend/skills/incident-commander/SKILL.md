---
name: incident-commander
description: 主Agent调度技能，负责命令分解、证据收敛与决策闭环
triggers: 调度,命令,协同,收敛,裁决,验证,round,orchestrate
agents: ProblemAnalysisAgent
---

## Goal
- 在有限轮次下，把“分散观点”收敛为“可执行结论”。

## Playbook
1. **首轮覆盖**：并行下发 Log/Domain/Code/Database/Metrics，避免单源偏差。
2. **命令具体化**：每条命令必须包含 `task/focus/expected_output/use_tool`。
3. **冲突处理**：出现证据冲突时，调度 Critic + Rebuttal 再进入 Judge。
4. **强制约束**：若有 `database_tables`，必须下发给 DatabaseAgent。
5. **停机条件**：仅当 Top-K 根因 + 修复方案 + 验证方案齐备时停止。

## Quality Gate
- 禁止空转命令（如“继续分析”但无 focus）。
- 禁止跳过关键数据源。
- 若信心不足，必须明确补证动作和截止条件。

## Output Contract
- `chat_message`: 主持人口吻的简短调度说明。
- `commands`: 1~5 条可执行命令。
- `analysis`: 当前证据收敛状态（充分/冲突/缺口）。
- `conclusion`: 下一步（继续讨论/进入裁决/停止）。
