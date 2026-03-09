# 2026-03-09 Agent Focused Context Implementation Plan

- [x] 放宽 runtime 与 session compaction 的长度、列表上限
- [x] 在 `AgentToolContextService` 中新增 focused context 构建能力
- [x] 为 Code/Log/Domain/Database/Metrics/Change/Runbook 构造专属 focused context
- [x] 在 runtime `_build_agent_context_with_tools()` 中注入 `focused_context`
- [x] 调整 prompt 模板，显式展示 `focused_context`
- [x] 提高专家 Agent 的 history/token 预算
- [x] 补充 focused context 与 compaction 测试
- [x] 运行后端测试与前端构建验证
