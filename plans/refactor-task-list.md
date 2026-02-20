# 重构任务清单（基于当前改进方案）

## R0 已完成（本轮已落地）
- [x] 代码先推送到 GitHub 备份（`origin/main`）
- [x] 引入本地文件持久化仓储（Incident / Debate / Report），默认启用 `file` 模式
- [x] 清理运行配置中的 AutoGen 历史残留，统一为 `LLM_*` 环境变量

## R1 架构与编排（P0）
- [x] 将当前串行编排重构为“并行分析 + 顺序裁决”执行图（Log/Domain/Code 并行）
- [x] 引入可恢复任务状态机（pending/running/waiting/retrying/completed/failed/cancelled）
- [x] 统一事件模型（event_id, trace_id, phase, agent, payload_version）
- [x] 增加任务中断与恢复能力（WebSocket 断开后可继续/重连恢复）

## R2 LLM 调用稳定性（P0）
- [x] 增加调用级重试策略（幂等重试、指数退避、抖动）
- [x] 增加超时分层（连接超时、请求超时、总流程超时）
- [x] 增加结构化输出兜底（JSON 修复器 + 二次格式化提示）
- [x] 增加 token 预算控制（不同 agent 上下文裁剪策略）

## R3 责任田与资产链路（P1）
- [x] 责任田映射结果在报告中强制落表展示（领域/聚合根/代码/表/设计引用）
- [x] 责任田命中失败时给出可执行补充引导（缺少 method/path/trace）
- [x] 案例检索增加同义词与模糊匹配，降低“误未命中”
- [x] 资产融合关系支持反向追溯（从表/类反查接口）

## R4 前端体验与可观测性（P1）
- [x] 流式事件面板支持按 agent/phase/type 过滤与检索
- [x] 报告页增加结构化卡片视图与高亮差异，不再以长文本为主
- [x] 历史页支持“分析中任务”进入详情页并实时查看
- [x] 增加前端 trace 展示（每次 LLM 请求的 trace_id、耗时、状态）

## R5 工程化与质量（P1）
- [x] 增加真实 LLM 小样本回归集（非 mock），覆盖主链路
- [x] 增加端到端自动化（创建事件 -> WS 辩论 -> 报告 -> 责任田验证）
- [x] 文档统一术语（AutoGen / LLM），移除 AutoGen/Claude 历史描述
- [x] 补充本地数据迁移与清理脚本（file store 版本化）

## 验证方式
1. `cd backend && pytest -q`
2. `RUN_LIVE_LLM_TESTS=1 pytest -q backend/tests/test_live_llm_regression.py`
3. `npm run smoke:e2e`
