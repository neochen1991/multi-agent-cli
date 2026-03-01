# 生产问题根因分析系统可执行任务清单

> 来源设计文档：`/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-01-production-rca-agent-brainstorm-design.md`  
> 执行范围：本地文件/内存存储，不引入外部数据库  
> 执行顺序：P0 -> P1 -> P2 -> P3 -> P4

---

## 0. 执行规则

1. 每个任务完成后必须做最小验证并提交一次小步 commit。  
2. 所有任务默认在当前 API 与前端交互不变前提下演进。  
3. 任何任务如果引入行为变化，必须补充事件日志字段与前端展示适配。  
4. 失败任务不得阻塞主干，允许开关降级但不能输出“无模型结论”报告。

---

## 1. 里程碑总览

| 里程碑 | 目标 | 预计周期 | 完成标准 |
|---|---|---|---|
| M1 (P0) | 稳定性与可观测打底 | 1-2 周 | 全链路可追踪、无重复消息、失败可定位 |
| M2 (P1) | 架构收敛与可测试 | 2-3 周 | 编排器减薄、状态收敛、核心单测补齐 |
| M3 (P2) | Agent 能力扩展 | 2-4 周 | 新 Agent 可参与协作并有工具证据 |
| M4 (P3) | 前端体验升级 | 1-2 周 | 三页职责清晰、聊天流可读、报告可视化 |
| M5 (P4) | 持续质量体系 | 持续 | 指标稳定、回归自动化、运维闭环 |

---

## 2. 可执行任务清单

## P0 稳定性与可观测（必须先完成）

### T-P0-01 统一事件 ID 与去重协议
- 优先级：P0
- 依赖：无
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/core/event_schema.py`
  - `backend/app/runtime/langgraph/event_dispatcher.py`
  - `frontend/src/pages/Incident/index.tsx`
- 执行步骤：
  - 后端所有事件补充稳定 `event_id` 生成逻辑。
  - WebSocket 与持久化事件统一使用同一 `event_id`。
  - 前端仅按 `event_id` 去重，去掉基于文本的弱去重主逻辑。
- 验收标准：
  - 同一事件不会重复展示。
  - 前端刷新后回放事件不重复。

### T-P0-02 统一 LLM 调用日志模型
- 优先级：P0
- 依赖：T-P0-01
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/runtime/langgraph/execution.py`
  - `backend/app/runtime/langgraph/event_dispatcher.py`
  - `backend/app/config.py`
- 执行步骤：
  - 统一日志字段：`session_id/agent_name/model/timeout/retry/latency_ms/prompt_len`。
  - 统一中文日志摘要，避免 `\uXXXX` 不可读输出。
  - 增加 `llm_request_started/llm_request_completed/llm_request_failed` 标准事件别名。
- 验收标准：
  - `backend.log` 可直接阅读中文。
  - 任一 Agent 一次调用可在日志中串联完整生命周期。

### T-P0-03 严格禁止“无有效模型结论直接出报告”
- 优先级：P0
- 依赖：无
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/services/debate_service.py`
  - `backend/app/services/report_service.py`
  - `frontend/src/pages/Incident/index.tsx`
- 执行步骤：
  - 在辩论结果落盘前校验有效结论字段。
  - 无有效结论时返回明确错误态与可重试提示。
  - 前端结果页展示“缺少有效结论”的明确提示，不生成空报告。
- 验收标准：
  - 不再出现“模型未返回仍出报告”场景。

### T-P0-04 失败态快速诊断与重试入口
- 优先级：P0
- 依赖：T-P0-02
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/api/debates.py`
  - `backend/app/api/ws_debates.py`
  - `backend/app/services/debate_service.py`
  - `frontend/src/services/api.ts`
  - `frontend/src/pages/Incident/index.tsx`
- 执行步骤：
  - 标准化 `session_failed` 事件内容（error_code/error_message/phase）。
  - 支持“仅重试失败 Agent”接口参数（保留默认全量重跑）。
  - 前端提供失败任务快速重试按钮。
- 验收标准：
  - 失败后 1 次点击可触发可观测重试。

### T-P0-05 P0 回归与冒烟
- 优先级：P0
- 依赖：T-P0-01~04
- 状态：✅ 已完成（2026-03-01，完整前后端+WS+报告链路冒烟通过）
- 变更文件：
  - `scripts/smoke-e2e.mjs`
  - `plans/test-matrix.md`
- 执行步骤：
  - 增加重复消息校验、无结论报告拦截校验。
  - 本地跑通 API+WS+前端流程（场景：`order-502-db-lock`、`order-404-route-miss`、`payment-timeout-upstream`，通过率 100%）。
- 验收标准：
  - smoke 脚本一次通过。

---

## P1 架构收敛与可测试

### T-P1-01 拆分编排器职责
- 优先级：P1
- 依赖：P0 完成
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/runtime/__init__.py`
  - `backend/app/services/__init__.py`
  - `backend/app/runtime/langgraph_runtime.py`
  - `backend/app/runtime/langgraph/builder.py`
  - `backend/app/runtime/langgraph/nodes/*.py`
  - `backend/app/runtime/langgraph/routing_strategy.py`
  - `backend/app/runtime/langgraph/services/state_transition_service.py`
- 执行步骤：
  - 将图构建、路由决策、节点执行、事件派发分别收敛到独立模块。
  - `langgraph_runtime.py` 仅保留装配与生命周期控制。
- 验收标准：
  - `langgraph_runtime.py` 行数明显下降，逻辑分层清晰。

### T-P1-02 状态模型收敛（messages 主通道）
- 优先级：P1
- 依赖：T-P1-01
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/runtime/langgraph/state.py`
  - `backend/app/runtime/langgraph/message_ops.py`
  - `backend/app/runtime/langgraph/nodes/agents.py`
  - `backend/app/runtime/langgraph/services/state_transition_service.py`
  - `backend/app/runtime/langgraph_runtime.py`
- 执行步骤：
  - 统一以 `messages` 作为主对话状态。
  - `history_cards` 改为投影字段，由节点或 reducer 派生。
- 验收标准：
  - 不再出现同一信息双轨更新冲突。

### T-P1-03 统一 AgentFactory 与执行路径
- 优先级：P1
- 依赖：T-P1-01
- 状态：✅ 已完成（2026-03-01，统一为 direct ChatOpenAI 执行路径）
- 变更文件：
  - `backend/app/runtime/langgraph/execution.py`
- 执行步骤：
  - 明确单一路径：Factory 模式或 Direct 模式（二选一主路径）。
  - 清理未使用分支与冗余参数。
- 验收标准：
  - 每次调用路径在日志中唯一可见。

### T-P1-04 并行分析 fan-out/fan-in 标准化
- 优先级：P1
- 依赖：T-P1-02
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/runtime/langgraph/phase_executor.py`
  - `backend/app/runtime/langgraph/nodes/agent_subgraph.py`
- 执行步骤：
  - 将并行执行统一收敛到 fan-out/fan-in 结构。
  - 聚合节点统一合并结果并回传主 Agent。
- 验收标准：
  - 三专家并行执行时间显著低于串行。

### T-P1-05 核心单元测试补齐
- 优先级：P1
- 依赖：T-P1-01~04
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/tests/test_state_transition_service.py`
  - `backend/tests/test_event_schema_stability.py`
  - `backend/tests/test_report_guard.py`
  - `backend/tests/test_specs_expanded_agents.py`
  - `backend/tests/test_agent_runner_fatal.py`
- 执行步骤：
  - 覆盖路由策略、状态 reducer、失败重试、报告门禁。
- 验收标准：
  - 新增关键测试可在本地稳定通过。

---

## P2 Agent 能力扩展

### T-P2-01 新增 MetricsAgent
- 优先级：P2
- 依赖：P1 完成
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/runtime/langgraph/specs.py`
  - `backend/app/runtime/langgraph/prompts.py`
  - `backend/app/runtime/langgraph/builder.py`
  - `backend/app/services/agent_tool_context_service.py`
- 执行步骤：
  - 增加 agent spec、prompt、路由接入。
  - 接入监控快照输入解析（先支持本地文本输入）。
- 验收标准：
  - 主 Agent 可下发 Metrics 分析指令并收到反馈。

### T-P2-02 新增 ChangeAgent
- 优先级：P2
- 依赖：T-P2-01
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/runtime/langgraph/specs.py`
  - `backend/app/services/agent_tool_context_service.py`
  - `backend/app/runtime/langgraph/prompts.py`
- 执行步骤：
  - 支持变更窗口识别（Git 最近提交摘要）。
  - 输出可疑变更候选与置信度。
- 验收标准：
  - 变更关联证据可在事件流中展示。

### T-P2-03 新增 RunbookAgent
- 优先级：P2
- 依赖：T-P2-01
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/tools/case_library.py`
  - `backend/app/runtime/langgraph/specs.py`
  - `backend/app/services/agent_tool_context_service.py`
- 执行步骤：
  - 从本地案例库检索相似故障与处置步骤。
  - 输出 SOP 建议和差异点。
- 验收标准：
  - 至少返回一条可执行 SOP 建议。

### T-P2-04 新增 VerificationAgent
- 优先级：P2
- 依赖：T-P2-01~03
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/runtime/langgraph/specs.py`
  - `backend/app/runtime/langgraph/prompts.py`
  - `backend/app/runtime/langgraph/parsers.py`
  - `backend/app/runtime/langgraph/routing_helpers.py`
  - `backend/app/runtime/langgraph/routing/rules_impl.py`
  - `backend/app/runtime/langgraph_runtime.py`
  - `backend/app/services/debate_service.py`
  - `frontend/src/pages/Incident/index.tsx`
- 执行步骤：
  - 在裁决后生成验证计划：功能/性能/回归/回滚。
- 验收标准：
  - 结果页出现“验证计划”结构化内容。

### T-P2-05 证据引用 ID 与跨源校验
- 优先级：P2
- 依赖：T-P2-01~04
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/runtime/langgraph/parsers.py`
  - `backend/app/models/debate.py`
  - `backend/app/services/debate_service.py`
  - `backend/app/services/report_service.py`
- 执行步骤：
  - 统一 evidence_id 与 source_ref。
  - Judge 输出必须引用跨源证据（日志+代码/领域）。
- 验收标准：
  - 报告中每条核心结论可追溯证据来源。

---

## P3 前端体验升级

### T-P3-01 Incident 页面组件化拆分
- 优先级：P3
- 依赖：P1 完成
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `frontend/src/pages/Incident/index.tsx`
  - `frontend/src/components/incident/*`（新增）
- 执行步骤：
  - 拆分为：资产映射、聊天流、事件明细、结果报告组件。
- 验收标准：
  - 页面复杂度下降，单组件职责清晰。

### T-P3-02 聊天流消息卡片模型统一
- 优先级：P3
- 依赖：T-P3-01
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `frontend/src/pages/Incident/index.tsx`
  - `frontend/src/styles/global.css`
- 执行步骤：
  - 命令卡/分析卡/工具卡/反馈卡统一渲染协议。
  - 默认摘要，支持“展开详情”。
- 验收标准：
  - 不再直出 JSON；最后一行丢失问题消失。

### T-P3-03 报告卡片化展示优化
- 优先级：P3
- 依赖：T-P3-01
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `frontend/src/pages/Incident/index.tsx`
  - `frontend/src/components/incident/DebateResultPanel.tsx`
  - `frontend/src/services/api.ts`
- 执行步骤：
  - 报告拆分为根因/证据/影响/建议/验证计划卡片。
- 验收标准：
  - 用户无需阅读 Markdown 原文即可完成决策。

### T-P3-04 北京时间显示一致性治理
- 优先级：P3
- 依赖：无
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `frontend/src/utils/dateTime.ts`
  - `frontend/src/pages/Home/index.tsx`
  - `frontend/src/pages/Incident/index.tsx`
- 执行步骤：
  - 统一时间解析规则与展示文案。
- 验收标准：
  - 首页、分析页、历史页时间统一为北京时间。

---

## P4 质量体系与运维闭环

### T-P4-01 构建故障回放样本集
- 优先级：P4
- 依赖：P2 完成
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `plans/test-matrix.md`
  - `plans/operations-runbook.md`
  - `backend/tests/fixtures/*`（新增）
- 执行步骤：
  - 补充真实故障样本（日志/堆栈/症状/预期根因）。
- 验收标准：
  - 至少 20 个样本可自动回放。

### T-P4-02 SLO 指标与告警阈值
- 优先级：P4
- 依赖：P0 完成
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `backend/app/core/observability.py`
  - `backend/app/services/debate_service.py`
  - `plans/operations-runbook.md`
- 执行步骤：
  - 指标：成功率、P95 时长、超时率、重试率、无效结论率。
- 验收标准：
  - 可从日志或指标接口计算并对比版本变化。

### T-P4-03 E2E 回归流水线脚本
- 优先级：P4
- 依赖：T-P4-01
- 状态：✅ 已完成（2026-03-01）
- 变更文件：
  - `scripts/smoke-e2e.mjs`
  - `package.json`
- 执行步骤：
  - 增加分场景回归命令与失败报告输出。
- 验收标准：
  - 一键运行可输出通过率与失败明细。

---

## 3. 执行顺序建议（可直接照此推进）

1. 第一周：T-P0-01 ~ T-P0-05。  
2. 第二到三周：T-P1-01 ~ T-P1-05。  
3. 第四到五周：T-P2-01 ~ T-P2-05。  
4. 第六周：T-P3-01 ~ T-P3-04。  
5. 持续：T-P4-01 ~ T-P4-03。

---

## 4. 每日执行模板（建议）

1. 选择 1-2 个任务（同一优先级内）。  
2. 实现 + 本地验证 + 更新任务状态。  
3. 记录风险与阻塞。  
4. 提交代码并附任务 ID（如 `feat: T-P0-02 unify llm event logs`）。
