# Event Dedupe Strategy (P0-3)

## 目标

统一后端事件标识与前端去重规则，避免以下问题：

- 同一事件在实时流与回放流中重复展示。
- WebSocket 控制类消息（`ack/error/pong/snapshot/result`）无稳定主键导致重复气泡。
- `agent_chat_message` 与流式输出事件跨通道重复渲染。

## 后端规则

文件：`/Users/neochen/multi-agent-cli_v2/backend/app/core/event_schema.py`

1. `event_id`
- 由稳定字段构建哈希（优先：`session_id + event_sequence + type`，并纳入 `stream_id/chunk_index`）。
- 当缺少 `event_sequence` 时才回退使用 `timestamp` 参与哈希。

2. `dedupe_key`
- 面向前端去重使用：
  - 常规：`{session_id}:{event_sequence}:{type}`
  - 流式 chunk：附加 `:{stream_id}:{chunk_index}`
  - 兜底：`{type}:{phase}:{agent}:{stream_id}:{chunk_index}`

3. 所有 WS 控制类消息统一携带事件字段
- 文件：`/Users/neochen/multi-agent-cli_v2/backend/app/api/ws_debates.py`
- `ack/error/pong` 统一返回 `data` 且包含 `event_id/dedupe_key/trace_id/timestamp`。
- `snapshot/result` 保持 `data` 事件信封一致。

## 前端规则

文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`

1. 去重优先级
- 第一优先：`dedupe_key`
- 第二优先：`event_id`
- 第三优先：历史 `fingerprint`

2. 去重集合生命周期
- 新建会话、切换会话、初始化会话时清空 `seenEventDedupeKeysRef/seenEventIdsRef/seenEventFingerprintsRef`。
- 加载持久化 `event_log` 时回填 `dedupe_key/event_id` 到集合。

3. 控制类消息数据源
- `ack/error` 优先使用 `payload.data` 入 `appendEvent`，确保统一命中去重键。

## 验证项

1. 后端编译：`cd backend && python3 -m compileall -q app` 通过。  
2. 前端类型：`cd frontend && npm run typecheck` 通过。  
3. 前端构建：`cd frontend && npm run build` 通过。  
4. 预期效果：
- 相同事件在重连/回放后不重复生成对话气泡。
- `ack/error` 不再因缺失稳定键导致重复展示。
