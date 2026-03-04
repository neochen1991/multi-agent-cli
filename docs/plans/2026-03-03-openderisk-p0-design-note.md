# P0 Design Note - Runtime Standardization

## Scope
- message-first 状态主轴收敛
- 编排器初始化状态集中化
- 事件去重协议统一（`event_id/dedupe_key`）

## Implementation
- `history_cards` 降级为展示投影，节点上下文优先从 `messages` 推导。
- 统一初始化构造 `build_session_init_update()`。
- WebSocket 控制消息与业务消息统一事件信封，前端优先 `dedupe_key` 去重。

## Verification
- 后端 `python3 -m compileall -q app`
- 前端 `npm run typecheck && npm run build`
