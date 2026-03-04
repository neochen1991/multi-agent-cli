# OpenDerisk-Aligned Optimization Checklist v2

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有基础上继续对齐 OpenDerisk 的架构与功能，实现“可持续演进、可治理、可观测”的生产故障 RCA 平台。

**Architecture:** 继续沿 `runtime_core / runtime_ext / runtime_serve` 三层推进，收敛运行时单入口；将 Skill/Resource/MCP/Session-Mode 的平台能力产品化到 API 与前端工作台，形成闭环。

**Tech Stack:** FastAPI, LangGraph, Pydantic, TypeScript + React + Ant Design, 本地文件存储（无外部 DB）。

---

## 0. 基线结论（当前状态）

- 已完成：WorkLog 注入、Prune 统计、MCP 生命周期 API、quick/background/async 模式入口、输出 ref 回查、治理看板增强。
- 仍需优化：  
1. 运行时“标准 LangGraph messages 流转”仍有 `history_cards` 辅助路径，状态模型仍偏混合。  
2. MCP 生命周期虽有接口，但缺少“真实 connect/list_tools/call_tool”与连接保活治理。  
3. 前端会话模式与工具生命周期的“操作可见性”仍不足（可用但不完整）。  
4. 与 OpenDerisk 的“平台化治理+运行机制”相比，还缺标准化对外集成与更完整的回放审计视图。

---

## P0（高优先，1-2周）运行时标准化收敛

### P0-1 收敛为单一状态主轴（MessagesState 优先）
- [x] 将 `history_cards` 从“主状态”降级为“展示派生状态”，统一以 `messages + outputs` 作为编排真源。
- [x] 清理重复状态字段（同义字段只保留一份），减少跨模块同步成本。
- 主要文件：
  - `backend/app/runtime/langgraph/state.py`
  - `backend/app/runtime/langgraph/services/state_transition_service.py`
  - `backend/app/runtime/langgraph_runtime.py`
- 验收：
  - Agent 协作依赖 `messages` 自动流转可追踪，`history_cards` 仅用于 UI 视图构建。
- 完成记录（2026-03-03，子项1）：
  - 变更文件：
    - `backend/app/runtime/langgraph_runtime.py`
    - `backend/app/runtime/langgraph/nodes/agents.py`
    - `backend/app/runtime/langgraph/nodes/supervisor.py`
    - `backend/app/runtime/langgraph/nodes/agent_subgraph.py`
  - 自测结果：
    - `cd backend && python3 -m compileall -q app` 通过
- 完成记录（2026-03-03，子项2）：
  - 变更文件：
    - `backend/app/runtime/langgraph/state.py`
    - `backend/app/runtime/langgraph_runtime.py`
  - 说明：
    - 新增 `build_session_init_update()`，由状态层统一构建初始化字段，避免编排器手工重复拼接同义状态。

### P0-2 编排器进一步瘦身（只保留“协调”）
- [x] 把剩余的 prompt 调度拼装逻辑继续下沉到 `prompt_builder/nodes/services`。
- [x] 将 `langgraph_runtime.py` 控制在协调职责，避免继续膨胀。
- 主要文件：
  - `backend/app/runtime/langgraph_runtime.py`
  - `backend/app/runtime/langgraph/nodes/*.py`
  - `backend/app/runtime/langgraph/services/*.py`
- 验收：
  - 运行链路清晰：Builder -> Nodes -> AgentRunner -> EventDispatcher。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/runtime/langgraph/nodes/agents.py`
    - `backend/app/runtime/langgraph/nodes/supervisor.py`
    - `backend/app/runtime/langgraph/nodes/agent_subgraph.py`
    - `backend/app/runtime/langgraph/services/state_transition_service.py`
  - 说明：
    - 节点层统一调用 `orchestrator._graph_apply_step_result`，编排器以协调为主，节点负责执行细节与状态更新。

### P0-3 对话与事件去重机制统一
- [x] 将前端去重规则与后端事件 ID/sequence 统一规范，减少跨端重复消息。
- [x] 为 `agent_chat_message`/`llm_stream_delta` 定义稳定唯一键策略文档。
- 主要文件：
  - `frontend/src/pages/Incident/index.tsx`
  - `backend/app/core/event_schema.py`
  - `backend/app/runtime/langgraph/event_dispatcher.py`
- 验收：
  - 同一消息不会在对话区重复展示；重连后不会回放重复气泡。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/core/event_schema.py`
    - `backend/app/api/ws_debates.py`
    - `frontend/src/pages/Incident/index.tsx`
    - `docs/plans/2026-03-03-event-dedupe-strategy.md`
  - 自测结果：
    - `cd backend && python3 -m compileall -q app` 通过
    - `cd frontend && npm run typecheck` 通过
    - `cd frontend && npm run build` 通过

### P0-4 超时恢复与预算收敛（补充）
- [x] 修复 `quick/economy` 模式下总超时后误判失败的问题：若已有有效 Judge 结论则回收并继续完成会话。
- [x] 修复预算耗尽后 `JudgeAgent` 循环调用：达到预算且已有可用裁决时直接收敛结束。
- [x] 收紧 quick 模式讨论步数，避免长时间 `debating`。
- 主要文件：
  - `backend/app/services/debate_service.py`
  - `backend/app/runtime/langgraph/routing_helpers.py`
  - `backend/app/runtime/langgraph_runtime.py`
- 验收：
  - `payment-timeout-upstream` 不再长期 pending/WS 超时；
  - 三个 smoke 场景均可完成并产出有效结论。
- 完成记录（2026-03-03）：
  - 自测结果：
    - `cd backend && python3 -m compileall -q app` 通过
    - `SMOKE_SCENARIO=payment-timeout-upstream` 通过
    - `SMOKE_SCENARIO=order-502-db-lock` 通过
    - `SMOKE_SCENARIO=order-404-route-miss` 通过

---

## P1（高优先，2周）MCP 与工具平台能力对齐 OpenDerisk

### P1-1 MCP 连接管理能力补齐
- [x] 新增 `connect/disconnect/list_tools/call_tool` 语义接口（在现有 registry 生命周期之上）。
- [x] 每个 connector 增加保活探测、失败重连、错误分级。
- 主要文件：
  - `backend/app/runtime/tool_registry/registry.py`
  - `backend/app/api/settings.py`
  - `backend/app/runtime/connectors/*.py`
- 验收：
  - 能看到“已连接工具集”与调用结果，不只停留在配置层。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/runtime/tool_registry/registry.py`
    - `backend/app/api/settings.py`
    - `frontend/src/services/api.ts`
    - `frontend/src/pages/ToolsCenter/index.tsx`
  - 说明：
    - 已提供连接器级 connect/disconnect/list_tools/call_tool API，含探测时间、重连计数、错误等级。

### P1-2 工具调用审计标准化
- [x] 统一工具审计格式：request/response/status/duration/error/ref_id。
- [x] 工具大输出统一落 `output_ref`，前端审计页可按 ref 展开。
- 主要文件：
  - `backend/app/runtime/langgraph/output_truncation.py`
  - `backend/app/runtime/trace_lineage/recorder.py`
  - `frontend/src/pages/ToolsCenter/index.tsx`
- 验收：
  - 工具调用记录可复盘且可核验“真实返回内容”。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/runtime/langgraph/event_dispatcher.py`
    - `frontend/src/components/tools/ToolAuditPanel.tsx`
    - `frontend/src/pages/ToolsCenter/index.tsx`
  - 说明：
    - 工具审计 payload 已标准化；超长响应写入 `output_ref`，前端支持“查看完整输出”。

### P1-3 工具授权与安全策略增强
- [x] 针对远程 git/http 工具，增加 allowlist + token 使用范围限制 + 脱敏检查。
- [x] 审计项补充“执行路径（本地/远程）”和“权限判定结果”。
- 主要文件：
  - `backend/app/services/agent_tool_context_service.py`
  - `backend/app/runtime/tool_registry/models.py`
  - `backend/app/runtime/tool_registry/registry.py`
- 验收：
  - 无授权时工具不会执行且有明确拒绝原因。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/config.py`
    - `backend/app/services/agent_tool_context_service.py`
    - `backend/app/runtime/langgraph_runtime.py`
  - 说明：
    - 新增 Git host allowlist；工具上下文事件新增 `execution_path` 与 `permission_decision`。

---

## P2（中高优先，2周）会话模式与产品化工作台

### P2-1 会话模式端到端产品化
- [x] 前端创建会话时可选择 `quick/background/async/standard`。
- [x] 任务中心展示模式、状态、预计时长、取消/恢复策略。
- 主要文件：
  - `frontend/src/pages/Home/index.tsx`
  - `frontend/src/pages/Incident/index.tsx`
  - `frontend/src/services/api.ts`
- 验收：
  - 用户无需手动拼 API 参数即可使用多会话模式。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `frontend/src/pages/Home/index.tsx`
    - `frontend/src/pages/Incident/index.tsx`
    - `frontend/src/pages/History/index.tsx`
  - 说明：
    - 输入页与首页均可选执行模式；异步/后台模式接入任务轮询；历史页展示模式与 ETA 并支持取消。

### P2-2 战情页对齐 OpenDerisk “工作台”交互
- [x] 同屏联动：时间线、工具调用、证据链、主结论、报告摘要。
- [x] 新增“关键决策跳转”能力（点击决策 -> 定位对应事件/证据）。
- 主要文件：
  - `frontend/src/pages/WarRoom/index.tsx`
  - `frontend/src/components/incident/*.tsx`
- 验收：
  - 一屏可完成调查、定位、复盘，不需跨页找信息。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `frontend/src/pages/WarRoom/index.tsx`
  - 说明：
    - 新增关键结论跳转过滤、报告摘要面板、时间线过滤联动。

### P2-3 回放体验增强
- [x] 增加“按阶段回放”和“按 Agent 回放”筛选器。
- [x] 回放时间线支持展开原始事件与 payload（脱敏后）。
- 主要文件：
  - `backend/app/api/debates.py`
  - `backend/app/runtime/trace_lineage/replay.py`
  - `frontend/src/pages/GovernanceCenter/index.tsx`
- 验收：
  - 任一 session 可快速重建决策路径与证据引用链。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/api/debates.py`
    - `backend/app/runtime/trace_lineage/replay.py`
    - `frontend/src/pages/InvestigationWorkbench/index.tsx`
  - 说明：
    - replay API 支持 phase/agent 过滤；工作台已可按阶段和 Agent 回放。

---

## P3（中优先，2-3周）治理、评测与持续优化

### P3-1 Benchmark 维度升级
- [x] 除失败率/超时率外，增加“证据跨源率、Top-K命中率、空结论率分场景”。
- [x] 评分结果与 PR/commit 关联，回归可定位到具体版本。
- 主要文件：
  - `backend/app/benchmark/*.py`
  - `scripts/benchmark-gate.py`
  - `.github/workflows/ci.yml`
- 验收：
  - Benchmark 不仅阻断，还能解释“为什么退化”。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/benchmark/fixtures.py`
    - `backend/app/benchmark/scoring.py`
    - `backend/app/benchmark/runner.py`
    - `scripts/benchmark-gate.py`
    - `.github/workflows/ci.yml`
  - 说明：
    - 新增 `top3_rate`、`cross_source_evidence_rate`、`empty_conclusion_by_scenario`，gate 支持阈值校验。

### P3-2 治理中心指标完善
- [x] 增加团队维度 token 成本趋势图、超时 hotspot、工具失败 TopN。
- [x] 增加 session SLA（首条证据延迟、首结论延迟、完整报告延迟）。
- 主要文件：
  - `backend/app/services/governance_ops_service.py`
  - `frontend/src/pages/GovernanceCenter/index.tsx`
- 验收：
  - 治理看板可支撑日常运维与成本治理决策。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/services/governance_ops_service.py`
    - `frontend/src/pages/GovernanceCenter/index.tsx`
  - 说明：
    - 新增 `token_cost_trend`、`timeout_hotspots`、`tool_failure_topn`、`sla` 并在治理中心展示。

### P3-3 外部协同深度化
- [x] 规范 Jira/ServiceNow/Slack/飞书双向字段映射模板。
- [x] 故障会话与工单状态自动同步（可关闭）。
- 主要文件：
  - `backend/app/api/governance.py`
  - `backend/app/services/governance_ops_service.py`
- 验收：
  - 故障分析结果可自动沉淀到外部流程系统。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/api/governance.py`
    - `backend/app/services/governance_ops_service.py`
    - `frontend/src/services/api.ts`
    - `frontend/src/pages/GovernanceCenter/index.tsx`
  - 说明：
    - 外部协同新增模板查询与自动同步开关配置。

---

## P4（中长期）OpenDerisk 机制深度对齐

### P4-1 ReActMaster 机制完善
- [x] DoomLoop/Compaction/Prune/Truncation/PhaseManager 的配置化策略中心。
- [x] 按场景模板切换运行策略（高并发、超时敏感、低成本）。
- 主要文件：
  - `backend/app/runtime/langgraph/*.py`
  - `backend/app/config.py`
- 验收：
  - 运行策略可按 incident 场景动态选择并可观测。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/runtime/langgraph/strategy_center.py`
    - `backend/app/services/debate_service.py`
    - `backend/app/api/governance.py`
    - `frontend/src/services/api.ts`
    - `frontend/src/pages/GovernanceCenter/index.tsx`
  - 说明：
    - 新增运行策略中心，支持 profile 列表/激活/切换，并在创建会话时按场景选择策略注入上下文。

### P4-2 Skill + Resource 生态化
- [x] 为更多业务域输出 Skill 包（模板、规则、禁用项、输出契约）。
- [x] Resource 层支持统一装配不同资产源（本地文件优先，可插拔外部源）。
- 主要文件：
  - `backend/app/runtime/langgraph/skills/`
  - `backend/app/services/asset_knowledge_service.py`
- 验收：
  - 新领域接入成本可控，复用路径清晰。
- 完成记录（2026-03-03）：
  - 变更文件：
    - `backend/app/runtime/langgraph/skills/order_timeout_rca/SKILL.md`
    - `backend/app/services/asset_knowledge_service.py`
    - `backend/app/api/assets.py`
    - `frontend/src/services/api.ts`
    - `frontend/src/pages/Assets/index.tsx`
  - 说明：
    - 新增业务技能包与资源源入口 API，支持本地优先+外部可插拔资产装配。

---

## 执行顺序与门禁

1. `P0 -> P1 -> P2 -> P3 -> P4` 顺序执行，禁止跳级。  
2. 每完成一项必须更新状态并补“变更文件 + 自测结果”。  
3. 每个阶段结束至少执行：
   - 后端：`cd backend && python3 -m compileall -q app`
   - 前端：`cd frontend && npm run typecheck && npm run build`

---

## 交付产物要求

- Checklist 文件持续维护（本文件）。  
- 关键改造产出短设计说明（每阶段 1 份）。  
- 每阶段结束提供一次“与 OpenDerisk 对齐度”复盘（架构/功能/可观测/治理四维）。
