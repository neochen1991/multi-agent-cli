# 2026-03-08 故障分析后台持续执行实施计划

## Step 1. 统一前端执行入口

- 修改 `Incident` 页启动逻辑，统一调用 `execute-background`。
- 保留 `executionMode` 作为会话创建参数，不再决定是否走 WebSocket 执行。

## Step 2. 拆分“执行”和“订阅”

- 将当前 `startRealtimeDebate()` 调整为纯订阅函数。
- WebSocket URL 默认 `auto_start=false`。

## Step 3. 增加运行任务本地持久化

- 在前端为运行中任务增加 localStorage 记录。
- 支持保存、读取、清理当前 incident/session 对应任务引用。

## Step 4. 恢复观察逻辑

- 页面初始化时检查 localStorage 中的运行任务。
- 若 task 仍在运行，则自动恢复：
  - session 详情
  - WebSocket 订阅
  - task 轮询

## Step 5. 停止分析语义收口

- 停止按钮继续走 `cancel`。
- 页面卸载、路由切换、刷新不触发 cancel。
- 任务终态后自动清理本地运行引用。

## Step 6. 验证

- `npm run typecheck`
- `npm run build`
- 手工验证：启动分析 -> 切页 -> 返回 -> 观察同一任务 -> 点击停止
