---
name: code-path-analysis
description: 代码路径与异常传播分析技能，定位故障触发点和并发瓶颈
triggers: 代码,repo,git,method,transaction,connection,线程,锁,性能,deadlock
agents: CodeAgent,ChangeAgent
---

## Goal
- 将故障现象映射到可定位的代码锚点与触发机制。

## Playbook
1. 建立调用链：入口 API -> 应用服务 -> 仓储/依赖。
2. 检查边界：事务范围、连接申请与释放、线程池与重试策略。
3. 定位高风险：长事务、阻塞 I/O、热点锁、泄漏路径。
4. 对齐证据：把日志/指标窗口映射到触发条件。

## Evidence Standard
- 至少 2 个代码锚点（文件/方法/关键语句或提交）。
- 结论必须区分“直接根因”与“促发因素”。

## Output Contract
- `analysis`: 代码机制解释。
- `conclusion`: 根因候选与置信度。
- `evidence_chain`: 代码证据锚点。
