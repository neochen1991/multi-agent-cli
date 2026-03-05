---
name: log-forensics
description: 日志与堆栈取证技能，重建故障时间线并定位首个异常事件
triggers: 日志,堆栈,trace,timeout,502,error,异常,重试,connection
agents: LogAgent,RebuttalAgent,CriticAgent
---

## Goal
- 给出“首个异常 -> 扩散机制 -> 用户症状”的日志证据链。

## Playbook
1. 锁定时间窗：首错时间、峰值、恢复点。
2. 抽取关联键：traceId/requestId/sessionId/service/endpoint。
3. 识别模式：超时、重试风暴、连接池耗尽、锁等待、线程阻塞。
4. 合并堆栈与网关日志，找出首个可归责异常点。

## Evidence Standard
- 至少 2 条带时间戳+组件+关键文本的证据。
- 至少 1 条反证或冲突证据（若无，明确“未发现反证”）。

## Output Contract
- `analysis`: 日志侧因果链。
- `conclusion`: 日志维度最可能根因。
- `evidence_chain`: 结构化日志证据数组。
