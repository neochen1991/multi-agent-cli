---
name: architectural-critique
description: 架构质疑技能，识别证据缺口与因果推理漏洞
triggers: 质疑,反证,假设,漏洞,证据不足,逻辑跳跃,counterfactual
agents: CriticAgent
---

## Goal
- 避免错误收敛，提升结论可靠性。

## Playbook
1. 列出当前结论的核心假设。
2. 指出缺失证据与冲突证据。
3. 给出最小补证动作（成本低、收益高）。
4. 给替代解释与证伪标准。

## Quality Gate
- 质疑必须“可验证”，不能抽象否定。
- 至少一条质疑指向跨源证据冲突。

## Output Contract
- `analysis`: 关键质疑点。
- `conclusion`: 是否需要继续补证。
- `evidence_chain`: 质疑依据与反例引用。
