# P1 Design Note - MCP/Tool Platform

## Scope
- 补齐连接器生命周期：`connect/disconnect/list_tools/call_tool`
- 统一工具审计字段：`request/response/status/duration/error/ref_id`
- 增强远程工具安全：allowlist + 脱敏 + 权限判定可见

## Implementation
- 连接器状态下沉到 `tool_registry`，提供探测、重连计数、错误分级。
- 审计在 `event_dispatcher` 做统一封装，超长响应写入 `output_ref`。
- 工具中心新增连接器控制台与引用回查。

## Verification
- 后端 `python3 -m compileall -q app`
- 前端 `npm run typecheck && npm run build`
