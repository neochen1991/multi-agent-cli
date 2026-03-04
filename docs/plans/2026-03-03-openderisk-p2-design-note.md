# P2 Design Note - Session Mode & Workbench UX

## Scope
- 会话模式产品化：`standard/quick/background/async`
- 战情页增强：关键决策跳转 + 报告摘要
- 回放增强：按阶段/按 Agent 过滤

## Implementation
- 首页与故障输入页增加模式选择，后台/异步模式走 task 轮询。
- 历史页展示模式、预计耗时、取消操作。
- 回放接口支持 `phase/agent` 过滤并透传到前端调查工作台。

## Verification
- 后端 `python3 -m compileall -q app`
- 前端 `npm run typecheck && npm run build`
