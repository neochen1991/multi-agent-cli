# 实时辩论报错修复清单（2026-02-18）

## 目标
修复前端“实时辩论失败/快照 failed”问题，并完成前后端闭环验证。

## 任务清单
- [x] 读取 `.run/logs` 前后端日志并定位根因（`DEBATING` 状态枚举异常）
- [x] 修复后端辩论状态枚举缺失（新增 `DebateStatus.DEBATING`）
- [x] 修复 OpenCode 会话创建失败导致流程中断（降级到本地会话 ID）
- [x] 优化 LLM 不可用时的降级链路（跳过无效调用，避免连续 error 日志）
- [x] 增加前后端闭环联调脚本（前端可达 + WebSocket 实时辩论 + 报告 + 资产定位）
- [x] 修复一键启停脚本稳定性（`stop:all:force` 不再误退出；`start:all` 可复用已有 opencode）
- [x] 执行联调验证并确认会话状态为 `completed`

## 验证结论
- WebSocket 事件链路正常：`session_started -> ... -> debate_completed -> session_completed`
- 会话状态：`completed`
- 报告生成：成功（降级路径可用）
- 资产定位：命中 `order / OrderAggregate`
