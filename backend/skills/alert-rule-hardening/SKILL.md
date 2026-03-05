---
name: alert-rule-hardening
description: 告警规则加固技能，提供可落地阈值/窗口/抑制建议
triggers: 告警,阈值,窗口,抑制,误报,漏报,rule,报警风暴
agents: RuleSuggestionAgent,JudgeAgent
---

## Goal
- 把事故证据转成可执行告警规则，平衡漏报与噪声。

## Playbook
1. 选择关键指标（领先指标 + 结果指标）。
2. 定义阈值、持续时长、组合逻辑。
3. 设计抑制、去重、升级策略。
4. 给上线后噪声/成本影响评估和回滚条件。

## Output Contract
- `analysis`: 规则设计依据。
- `conclusion`: P0/P1/P2 告警策略。
- `evidence_chain`: 触发场景和历史事故映射。
