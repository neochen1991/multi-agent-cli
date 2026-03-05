---
name: db-bottleneck-diagnosis
description: 数据库瓶颈取证技能，分析索引、慢SQL、会话状态与锁等待
triggers: 数据库,postgres,sql,慢sql,top sql,锁,session,连接池,索引,pg
agents: DatabaseAgent,JudgeAgent
---

## Goal
- 判断数据库是主因还是被动承压，并给可验证方案。

## Playbook
1. 按责任田表优先级检索：表结构、索引、行热点。
2. 分析慢SQL/TopSQL：耗时、频次、扫描行、锁等待。
3. 分析会话状态：阻塞链、等待事件、连接池排队。
4. 关联上游压力：判断是 DB 自身瓶颈还是流量传导。

## Evidence Standard
- 至少 1 条表结构/索引证据 + 1 条 SQL/会话证据。
- 结论中必须包含可量化阈值（如连接占用、等待时长）。

## Output Contract
- `analysis`: 数据库侧因果链。
- `conclusion`: 主因判断 + 风险级别。
- `evidence_chain`: 表/SQL/等待事件证据。
