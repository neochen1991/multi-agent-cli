# P4 Design Note - Strategy Center & Skill/Resource Ecosystem

## Scope
- 策略中心：DoomLoop/Compaction/Prune/Truncation/Phase 模板化
- 按场景自动策略选择（高并发/超时敏感/低成本）
- Skill 与 Resource 扩展（本地优先，可插拔外部源）

## Implementation
- 新增 `runtime/langgraph/strategy_center.py`，提供 profile 列表/激活/选择。
- 会话创建阶段将 `runtime_strategy` 注入上下文，并透出治理配置入口。
- 新增技能包示例 `order_timeout_rca`，资产资源入口 API 支持源列表输出。

## Verification
- 后端 `python3 -m compileall -q app`
- 前端 `npm run typecheck && npm run build`
