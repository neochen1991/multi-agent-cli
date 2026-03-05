---
name: domain-responsibility-mapping
description: 责任田映射技能，完成接口到领域/聚合根/Owner 的定位与影响分析
triggers: 责任田,领域,聚合根,api,接口,owner,业务影响,cmdb
agents: DomainAgent,ProblemAnalysisAgent
---

## Goal
- 快速明确归属与业务影响，避免错误归责。

## Playbook
1. 依据 URL/方法匹配资产条目。
2. 映射特性-领域-聚合根-Owner-依赖服务。
3. 标注命中置信度与缺失字段。
4. 解释该领域机制如何导致当前故障现象。

## Evidence Standard
- 至少 1 条命中资产条目；若未命中必须给候选映射。
- 必须说明业务影响范围（功能/交易/用户）。

## Output Contract
- `analysis`: 映射路径与业务影响。
- `conclusion`: 责任田归属结论 + 置信度。
- `evidence_chain`: 资产条目引用。
