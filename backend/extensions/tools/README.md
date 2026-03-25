# Extension Tools

`ToolPluginGateway` 会扫描 `backend/extensions/tools/*/tool.json`，并在命中时执行对应入口脚本。

最小目录结构：

```text
backend/extensions/tools/<tool-id>/
  tool.json
  run.py
```

`tool.json` 示例字段：

- `tool_id`
- `name`
- `runtime`（当前支持 `python`）
- `entry`（默认 `run.py`）
- `timeout_seconds`
- `allowed_agents`

插件入口约定：

1. 从 `stdin` 读取 JSON 请求
2. 输出 JSON 对象到 `stdout`
3. 失败时返回非零退出码或输出 `{"success": false, "summary": "..."}`

## 生产根因分析推荐插件

- `upstream_timeout_chain`
  - 场景：跨服务调用超时、504、deadline exceeded。
  - 作用：抽取超时级联链路与首发上游候选。
- `db_lock_hotspot`
  - 场景：数据库死锁、锁等待、事务阻塞。
  - 作用：抽取热点表、阻塞方线索与锁证据强度。
- `release_regression_guard`
  - 场景：疑似发布后故障、回滚后恢复。
  - 作用：抽取发布标识与时序证据，评估发布相关性。
