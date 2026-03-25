---
name: timeout-cascade-rca
description: 上游超时级联根因定位技能
triggers: timeout,deadline,504,upstream,cascade,级联,超时
agents: LogAgent,MetricsAgent,DomainAgent,JudgeAgent
---

## Goal

在跨服务调用出现超时告警时，快速识别“首发上游”和“级联放大路径”。

## Checklist

1. 先列出超时信号与出现顺序，标注是否集中在同一服务链路。
2. 对比调用链中“先超时”的上游节点和“后扩散”的下游节点。
3. 明确写出证据充分度，避免把“症状服务”误判为“根因服务”。

## Output Contract

- `timeout_root_candidate`: 首发超时候选服务
- `cascade_path`: 级联路径（按时序）
- `evidence_strength`: `strong | medium | weak`
- `next_verification`: 下一步验证建议
