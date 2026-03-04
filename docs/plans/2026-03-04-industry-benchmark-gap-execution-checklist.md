# Industry-Benchmark Gap Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 对齐业界 SRE 智能体最新实践，补齐当前系统在可用性、准确率、自治修复与平台治理方面的关键差距。

**Architecture:** 以现有 LangGraph 多 Agent 运行时为核心，不引入外部数据库，优先改造状态治理、路由编排、证据推理、工具可观测与前端统一工作台。实施分 P0-P3 四层，先保证稳定可用，再提升结论质量与治理能力。

**Tech Stack:** FastAPI, LangGraph, LangChain ChatOpenAI-compatible API, React + Ant Design, local file store, GitHub Actions.

---

## 执行规则

- 状态字段：`TODO | DOING | DONE | BLOCKED`
- 每完成一个任务，必须在本文件将状态改为 `DONE` 并补充完成日期。
- 每个任务至少包含：代码改动、接口联调、前端可视化验证、日志验收。
- 默认不引入外部存储，持久化继续使用本地文件或内存。

---

### Task 1: 统一运行时状态模型（去重复状态）

**Priority:** P0  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/message_ops.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/services/state_transition_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`

**Implementation Steps:**
1. 约束 `DebateExecState` 为唯一真状态源，减少 `turns/history_cards/messages` 冗余同步。
2. 明确 reducer 语义：可累积字段、覆盖字段、派生字段分离。
3. 清理多处手动拼装 state 的逻辑，统一通过 state transition service。
4. 补充状态快照一致性测试。

**Acceptance Criteria:**
- 同一会话中不再出现状态源冲突导致的数据不一致。
- WS 快照、详情接口、报告生成读取同一份状态语义。

---

### Task 2: Orchestrator 进一步解耦（防上帝类）

**Priority:** P0  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/builder.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/phase_executor.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/agent_runner.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/services/routing_service.py`

**Implementation Steps:**
1. 将路由判定、事件分发、提示词装配、会话策略拆到独立 service。
2. orchestrator 只保留“生命周期协调 + graph invoke”。
3. 移除重复 helper，避免跨模块循环依赖。

**Acceptance Criteria:**
- `langgraph_runtime.py` 核心类职责显著收敛。
- 路由/执行/事件模块可独立单测。

---

### Task 3: 三层超时预算与降级策略

**Priority:** P0  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/execution.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/config.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`

**Implementation Steps:**
1. 增加 `queue timeout`、`llm call timeout`、`session total timeout` 三层预算。
2. 超时后按 agent 级别降级：重试 -> 轻量 prompt -> fallback turn。
3. 输出统一超时事件与可读错误原因。

**Acceptance Criteria:**
- 不再出现长期 pending。
- 超时会话可自动结束并给出可读降级结论。

---

### Task 4: 工具调用证据化与审计回放

**Priority:** P0  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/tool_registry/registry.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`

**Implementation Steps:**
1. 统一工具调用日志结构（请求摘要/响应摘要/耗时/失败码）。
2. 为每个工具调用生成 `call_id`，前后端可关联检索。
3. 前端显示“真实调用证据卡”。

**Acceptance Criteria:**
- 用户可在前端确认工具是否真实调用、调用了什么、拿到什么结果。

---

### Task 5: 告警自动调查 10 秒首证据保障

**Priority:** P0  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/api/incidents.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/core/task_queue.py`

**Implementation Steps:**
1. 告警入站后并行触发：会话创建 + 首批证据采集。
2. 增加首证据 SLA 事件（`first_evidence_at`）。
3. 前端显示“调查已开始 + 首证据时间”。

**Acceptance Criteria:**
- 自动拉起后 10 秒内可看到首批证据卡。

---

### Task 6: 因果推理层 v2（拓扑+传播）

**Priority:** P1  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/judgement/causal_score.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/judgement/topology_reasoner.py`

**Implementation Steps:**
1. 引入服务依赖拓扑和调用传播链打分。
2. 区分“共现”与“因果”证据权重。
3. 输出根因候选时附传播路径摘要。

**Acceptance Criteria:**
- Top1 命中率、Top3 命中率可观测提升。

---

### Task 7: 强制跨源证据门禁

**Priority:** P1  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/judgement/causal_score.py`

**Implementation Steps:**
1. 根因结论前进行跨源证据校验（日志 + 代码/领域/指标）。
2. 若不满足则自动补证回合（限定次数）。
3. 在结果中标记 `cross_source_passed`。

**Acceptance Criteria:**
- “需要进一步分析”占比下降。

---

### Task 8: Top-K 候选可解释增强

**Priority:** P1  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/models/debate.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateResultPanel.tsx`

**Implementation Steps:**
1. 为候选增加覆盖证据数、冲突点、不确定性来源。
2. 前端改造成结构化卡片，不展示原始 JSON。
3. 支持候选间对比视图。

**Acceptance Criteria:**
- Top-K 可视化可读，且每个候选都可追溯证据。

---

### Task 9: Agent 动态协作而非固定轮询

**Priority:** P1  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/routing/rule_engine.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/routing/rules_impl.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`

**Implementation Steps:**
1. 主 Agent 基于缺口动态分派专家，而非固定顺序。
2. 引入停机条件：证据饱和/置信收敛/超时预算。
3. 保留批判-反驳环节但按需触发。

**Acceptance Criteria:**
- 辩论过程具备“命令驱动 + 动态收敛”行为。

---

### Task 10: Prompt 工厂统一治理

**Priority:** P1  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompt_builder.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`

**Implementation Steps:**
1. 统一 prompt 模板入口，去掉散落拼接。
2. 按角色、阶段、模式输出模板版本。
3. 增加 prompt 版本号写入日志。

**Acceptance Criteria:**
- prompt 来源可追踪，回归时可定位到模板版本。

---

### Task 11: 标准化数据源连接器（可开关）

**Priority:** P2  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/connectors/telemetry_connector.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/connectors/cmdb_connector.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/connectors/prometheus_connector.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/connectors/loki_connector.py`

**Implementation Steps:**
1. 保留本地文件模式默认开启。
2. 新增 Prometheus/Loki 连接器入口（默认关闭）。
3. 接口输出统一为可被 agent_tool_context_service 消费的规范。

**Acceptance Criteria:**
- 开关关闭时不影响现有流程，开启后可读取真实远程数据。

---

### Task 12: Checkpointer 与会话恢复增强

**Priority:** P2  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/checkpointer.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/api/ws_debates.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/task_registry.py`

**Implementation Steps:**
1. 明确 thread/session 恢复策略。
2. 异常中断后支持断点续跑与状态重建。
3. 前端恢复时给出“恢复自哪一步”。

**Acceptance Criteria:**
- 分析中断后可以继续，且不重复执行已完成步骤。

---

### Task 13: CI Benchmark Gate 指标升级

**Priority:** P2  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/.github/workflows/ci.yml`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/benchmark/scoring.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/scripts/benchmark-gate.py`

**Implementation Steps:**
1. 增加 top1/top3、超时率、空结论率、首证据时延门禁。
2. 输出趋势对比（与上次 baseline）。
3. 门禁失败阻断合并。

**Acceptance Criteria:**
- CI 可自动阻断质量回归。

---

### Task 14: 修复执行治理闭环强化

**Priority:** P2  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/remediation_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/api/governance.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx`

**Implementation Steps:**
1. 强化状态机合法跃迁校验。
2. 高风险操作强制人工审批。
3. 回滚计划生成与执行审计统一展示。

**Acceptance Criteria:**
- 每个执行动作可审计、可回滚、可追责。

---

### Task 15: 多租户治理增强（本地模式）

**Priority:** P2  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/governance_ops_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/api/governance.py`

**Implementation Steps:**
1. RBAC、配额、预算、隔离策略可配置。
2. 输出团队维度成本和成功率面板。
3. 增加按团队检索审计记录。

**Acceptance Criteria:**
- 可按团队追踪成本、风险和执行成功率。

---

### Task 16: 调查工作台/战情页合并

**Priority:** P3  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/WarRoom/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/router/index.tsx`

**Implementation Steps:**
1. 合并重复能力，统一为“调查工作台”。
2. 保留同屏：时间线、工具调用、结论、报告。
3. 路由兼容旧链接。

**Acceptance Criteria:**
- 用户无需在两个页面切换即可完成完整调查。

---

### Task 17: 辩论过程 Discord 风格对话流

**Priority:** P3  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`

**Implementation Steps:**
1. 消息分组按 agent + 时间。
2. 默认展示摘要，支持展开完整内容。
3. 去重渲染，修复重复消息/截断问题。

**Acceptance Criteria:**
- 前端不再重复展示消息，且可读性明显提升。

---

### Task 18: 报告可视化重构（非 Markdown 裸展示）

**Priority:** P3  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateResultPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`

**Implementation Steps:**
1. 报告分模块卡片化：根因、证据、修复、风险。
2. 加入证据链时间戳与来源标签。
3. 支持导出 markdown/pdf 但页面不直接裸渲染。

**Acceptance Criteria:**
- 报告页全部为结构化组件，无 JSON/原始文档直出。

---

### Task 19: 空状态与失败态友好化

**Priority:** P3  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/AssetMappingPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Home/index.tsx`

**Implementation Steps:**
1. 资产未命中/工具关闭/超时失败提供清晰提示。
2. 增加“下一步建议”按钮（重试、补充日志、切换模式）。
3. 首页关键按钮和提示态统一。

**Acceptance Criteria:**
- 不再出现空白区域或“功能开发中”文案。

---

### Task 20: 全链路北京时间统一

**Priority:** P3  
**Status:** DONE (2026-03-04)

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/core/observability.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/utils/time.ts`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Home/index.tsx`

**Implementation Steps:**
1. 后端日志输出增加统一时区字段。
2. 前端所有展示时间统一转 `Asia/Shanghai`。
3. 历史统计聚合按北京时间日界线。

**Acceptance Criteria:**
- 首页、会话、日志、报告的时间展示一致且为北京时间。

---

## 里程碑与验收

- **M1（P0）**：系统不再长期 pending，自动调查首证据 SLA 达标，工具调用可审计。
- **M2（P1）**：Top1/Top3 与跨源证据质量提升，动态协作稳定。
- **M3（P2）**：治理/CI 门禁/修复闭环可运行。
- **M4（P3）**：前端体验达到可读、可追溯、可操作。
