# 2026-03-08 故障分析后台持续执行设计

## 背景

当前故障分析页同时存在两种执行语义：

1. 前端直接通过 WebSocket 建连并触发实时执行。
2. 前端通过 `execute-background` / `execute-async` 提交后台任务后再轮询结果。

这会导致任务生命周期和页面生命周期混在一起。页面切换、刷新、WebSocket 断开虽然不一定立即取消任务，但前端心智仍然是“页面在驱动分析”。用户要求统一为：

- 故障分析一旦启动，应在后台持续分析直到结束。
- 页面切换、刷新、关闭当前页签都不应停止分析。
- 只有前端显式点击“停止分析”时才允许取消任务。

## 目标

1. 后台任务成为故障分析唯一执行载体。
2. WebSocket 只承担实时订阅和状态同步，不再承担自动启动执行。
3. 前端切换页面后返回，应能继续观察同一任务，而不是重新启动。
4. 显式停止分析时，才调用取消接口。

## 非目标

1. 不重写后端任务队列实现。
2. 不改动 Agent 调度、Prompt、工具门禁。
3. 不引入新的分布式任务系统。

## 方案

### 1. 启动路径统一为后台任务

- `Incident` 页点击“启动分析”时，一律调用 `POST /debates/{session_id}/execute-background`。
- 后端返回 `task_id` 后，前端把这次分析视为“后台持续运行任务”。
- `executionMode` 仍保留，用于创建会话时传给后端的策略参数；但不再决定是否走 WebSocket 执行。

### 2. WebSocket 改为纯订阅

- 前端建立 WebSocket 时默认传 `auto_start=false`。
- WebSocket 建连后只接收事件、快照和结果，不再隐式触发 `_run_debate_with_events`。
- 若需要恢复观察，前端直接重新连接同一 `session_id` 即可。

### 3. 前端持久化运行中的任务引用

前端在本地存一份运行中任务引用：

- `incident_id`
- `session_id`
- `task_id`
- `started_at`
- `mode`

用途：

- 路由切换后回到详情页时恢复观察。
- 浏览器刷新后重新挂载时继续轮询/订阅。
- 任务完成、失败、取消后自动清理。

### 4. 页面切换与关闭语义

- 页面卸载只关闭 WebSocket 订阅，不发送取消命令。
- 页面重新进入时，如果本地存在运行中任务引用，就自动：
  - 重新加载 session 详情。
  - 重新建立订阅。
  - 同时轮询 task 状态直到结束。

### 5. 停止语义

- 只有点击“停止分析”按钮，才调用 `/debates/{session_id}/cancel`。
- 取消成功后，清理本地任务引用并停止轮询。

## 关键实现点

### 前端

文件：`frontend/src/pages/Incident/index.tsx`

- 新增本地任务引用读写工具。
- `startAnalysisFromInput()` 改为统一提交 `execute-background`。
- `startRealtimeDebate()` 改为 `attachDebateStream()`，只负责连接订阅。
- `pollTaskUntilDone()` 在完成/失败/取消/进入人工审核后清理运行态。
- 页面初始化时检测是否存在当前 incident/session 的运行任务，自动恢复观察。

文件：`frontend/src/services/api.ts`

- `buildDebateWsUrl()` 改为支持 `auto_start` 参数，默认不自动启动。

文件：`frontend/src/components/incident/DebateProcessPanel.tsx`

- 文案从“启动实时辩论”调整为“启动分析”。

### 后端

本次不改动核心执行语义，只复用已有：

- `POST /debates/{session_id}/execute-background`
- `POST /debates/{session_id}/cancel`
- `GET /debates/tasks/{task_id}`
- WebSocket 快照与事件广播

## 验证标准

1. 点击“启动分析”后，即使切走页面，任务仍持续执行。
2. 回到故障详情页时，能看到同一个运行中任务的状态和事件。
3. 页面刷新不会触发新的分析任务。
4. 只有点击“停止分析”才会取消任务。
5. 人工审核、完成、失败、取消都能正确清理本地任务引用。
