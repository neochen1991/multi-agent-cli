---
name: final-judgment-synthesis
description: 最终裁决综合技能，生成 Top-K 根因与执行闭环
triggers: 裁决,root cause,top-k,置信度,最终结论,judge
agents: JudgeAgent,ProblemAnalysisAgent
---

## Goal
- 形成可执行、可追溯、可验证的最终裁决。

## Playbook
1. 产出 Top-K 根因候选（含置信度区间）。
2. 说明主结论胜出依据与其他候选排除理由。
3. 输出修复优先级（P0/P1/P2）与风险。
4. 输出验证闭环与回滚闭环。

## Quality Gate
- 不允许“需要进一步分析”空结论。
- 主结论必须引用跨源证据链。

## Output Contract
- `chat_message`: 主席裁决摘要。
- `final_judgment`: 根因、证据、修复、风险。
- `action_items`: 可执行动作清单。
