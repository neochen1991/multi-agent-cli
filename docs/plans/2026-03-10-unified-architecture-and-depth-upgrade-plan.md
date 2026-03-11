# Unified Architecture and Analysis Depth Upgrade Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不破坏现有功能契约的前提下，同时完成后端架构优化与多 Agent 分析深度升级，并同步补齐前端展示，使系统既更优雅可维护，又更接近生产级根因分析智能体。

**Architecture:** 先做“编排器瘦身 + 工具上下文拆层 + 状态与预算规则模块化”，为后续 `CodeAgent / LogAgent / DatabaseAgent / DomainAgent` 的深度增强提供清晰的承载结构。然后在此基础上实现多轮长程辩论机制、深度 focused context 和前端可视化补强。保持现有 API、WebSocket 事件主契约、quick 模式和现有页面入口兼容。

**Tech Stack:** Python 3.14, FastAPI, LangGraph, LangChain Core, pytest, React, TypeScript

---

## Why Combine These Two Workstreams

如果只做架构优化：
- 代码会更整洁，但分析深度问题仍然存在。

如果只做分析深度增强：
- 复杂逻辑会继续堆进 `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- 和 `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- 最终可读性和可维护性会进一步恶化。

因此统一改造顺序必须是：

1. 先冻结契约，保证重构不会破坏功能。
2. 先做必要的后端架构拆分。
3. 再在新结构上做深度分析增强。
4. 最后补前端多轮讨论与证据可视化。

## Workstreams

### Stream A: Architecture Cleanup

目标：
- 让 orchestrator 回归协调层
- 让 tool context service 回归路由层
- 把预算、状态投影、focused context、audit 变成独立模块

### Stream B: Analysis Depth Upgrade

目标：
- `CodeAgent` 升级为代码闭包分析
- `LogAgent` 升级为统一时序对齐
- `DatabaseAgent` 升级为锁等待图和执行计划分析
- `DomainAgent` 升级为领域约束推理
- 主 Agent 升级为多轮追问收敛控制器

### Stream C: Frontend Evidence Visualization

目标：
- 展示多轮辩论
- 展示主 Agent 追问
- 展示证据引用链
- 展示 Top-K 根因和证据覆盖

## Execution Order

### Phase 0: Contract Freeze

先冻结以下契约，避免后续拆分和增强时行为漂移：

- runtime state shape
- budget/timeout behavior
- `agent_tool_context_prepared` 事件 shape
- focused context shape
- structured output shape

### Phase 1: Runtime Refactor Foundation

优先拆分：

- `runtime_policy.py`
- `budgeting.py`
- `state_views.py`
- `context_facade.py`

并让：
- `LangGraphRuntimeOrchestrator` 只负责协调与生命周期
- nodes 通过 facade 与 orchestrator 协作

### Phase 2: Tool Context Refactor Foundation

优先拆分：

- `tool_context/router.py`
- `tool_context/providers/*.py`
- `tool_context/focused_context.py`
- `tool_context/audit.py`

并保留兼容入口：

- `AgentToolContextService.build_context(...)`
- `AgentToolContextService.build_focused_context(...)`

### Phase 3: Deep Agent Capability Upgrade

在架构拆分完成后，分别增强：

1. `CodeAgent`
2. `LogAgent`
3. `DatabaseAgent`
4. `DomainAgent`
5. cross-agent summaries

### Phase 4: Long-Running Debate Upgrade

新增：

- 多轮追问
- evidence coverage
- top-k hypotheses
- convergence score
- dynamic stop condition

### Phase 5: Frontend Visualization Upgrade

新增：

- 多轮讨论过程视图
- 主 Agent 追问关系
- 证据引用卡片
- Top-K 根因
- 因果链与覆盖图

### Phase 6: Regression and Smoke

完成后统一进行：

- 后端回归
- 前端构建
- smoke 场景
- 文档同步

## Unified Task List

### Task 1: Freeze Contracts Across Runtime and Agent Context

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_graph_builder.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_context_service.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_runtime_contracts.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_depth_contracts.py`

**Step 1: Write the failing tests**

冻结：
- runtime helper/state shape
- focused_context shape
- event shape
- quick/background/deep budget 契约

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/runtime/test_runtime_contracts.py \
  backend/tests/test_agent_depth_contracts.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

仅新增测试文件，不改生产逻辑。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/runtime/test_runtime_contracts.py \
  backend/tests/test_agent_depth_contracts.py \
  backend/tests/test_runtime_message_flow.py \
  backend/tests/test_agent_tool_context_service.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/tests/runtime/test_runtime_contracts.py backend/tests/test_agent_depth_contracts.py backend/tests/test_runtime_message_flow.py backend/tests/test_agent_tool_context_service.py backend/tests/test_graph_builder.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "test: freeze runtime and analysis depth contracts"
```

### Task 2: Extract Runtime Policy, Budgeting, and State Views

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/runtime_policy.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/budgeting.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state_views.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_runtime_policy.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_budgeting.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_state_views.py`

**Step 1: Write the failing test**

覆盖：
- runtime policy
- depth mode/budgeting
- state projection

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/runtime/test_runtime_policy.py \
  backend/tests/runtime/test_budgeting.py \
  backend/tests/runtime/test_state_views.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

从 orchestrator 下沉：
- `_configure_runtime_policy`
- `_agent_max_tokens`
- `_agent_timeout_plan`
- `_agent_http_timeout`
- `_agent_queue_timeout`
- `_history_cards_for_state`
- `_round_cards_for_routing`
- `_dialogue_items_from_messages`

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/runtime/test_runtime_policy.py \
  backend/tests/runtime/test_budgeting.py \
  backend/tests/runtime/test_state_views.py \
  backend/tests/test_runtime_message_flow.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/runtime/langgraph/runtime_policy.py backend/app/runtime/langgraph/budgeting.py backend/app/runtime/langgraph/state_views.py backend/app/runtime/langgraph_runtime.py backend/tests/runtime/test_runtime_policy.py backend/tests/runtime/test_budgeting.py backend/tests/runtime/test_state_views.py backend/tests/test_runtime_message_flow.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: extract runtime policy budgeting and state views"
```

### Task 3: Extract Tool Context Router, Providers, and Audit

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/router.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/audit.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/providers/code_provider.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/providers/log_provider.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/providers/domain_provider.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/providers/database_provider.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/providers/metrics_provider.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/providers/change_provider.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/providers/runbook_provider.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/services/tool_context/test_router.py`

**Step 1: Write the failing test**

覆盖 provider 路由和 audit 组装：
- Agent -> provider 映射
- command gate / permission / execution path 输出 shape

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/services/tool_context/test_router.py backend/tests/test_agent_tool_audit.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

将 `build_context` 大分支拆成：
- router
- provider
- audit builder

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/services/tool_context/test_router.py \
  backend/tests/test_agent_tool_audit.py \
  backend/tests/test_agent_tool_context_service.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/tool_context backend/app/services/agent_tool_context_service.py backend/tests/services/tool_context/test_router.py backend/tests/test_agent_tool_audit.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: split tool context router providers and audit"
```

### Task 4: Extract Focused Context Assemblers

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/focused_context.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/services/tool_context/test_focused_context.py`

**Step 1: Write the failing test**

覆盖：
- code/log/domain/database/metrics/change/runbook/cross-agent focused context

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/services/tool_context/test_focused_context.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

提取 focused context assembler：
- `CodeFocusedContextAssembler`
- `LogFocusedContextAssembler`
- `DomainFocusedContextAssembler`
- `DatabaseFocusedContextAssembler`
- `MetricsFocusedContextAssembler`
- `ChangeFocusedContextAssembler`
- `RunbookFocusedContextAssembler`
- `CrossAgentFocusedContextAssembler`

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/services/tool_context/test_focused_context.py \
  backend/tests/test_agent_tool_context_service.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/tool_context/focused_context.py backend/app/services/agent_tool_context_service.py backend/tests/services/tool_context/test_focused_context.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: extract focused context assemblers"
```

### Task 5: Deepen CodeAgent on Top of New Structure

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/code_analysis/source_loader.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/code_analysis/symbol_resolver.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/code_analysis/call_graph_builder.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/focused_context.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_context_service.py`

**Step 1: Write the failing test**

覆盖：
- `controller -> service -> dao`
- SQL 绑定
- downstream rpc/client
- transaction/pool/retry 风险点

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "code"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

`CodeAgent` 增加：
- `call_graph_summary`
- `sql_binding_summary`
- `downstream_rpc_summary`
- `resource_risk_points`
- `transaction_boundary_summary`

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "code"
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/code_analysis backend/app/services/tool_context/focused_context.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: deepen code agent topology closure analysis"
```

### Task 6: Deepen LogAgent, DatabaseAgent, and DomainAgent

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/log_analysis/timeline_extractor.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/log_analysis/trace_alignment.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/db_analysis/execution_plan_summary.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/db_analysis/lock_wait_graph.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/db_analysis/sql_pattern_cluster.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/domain_analysis/constraint_checks.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/focused_context.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_context_service.py`

**Step 1: Write the failing test**

覆盖：
- LogAgent: trace/span/instance/metric alignment
- DatabaseAgent: execution plan / lock graph / SQL clusters
- DomainAgent: invariant / constraint / transaction order reasoning

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "log or database or domain"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

补齐：
- `trace_timeline`
- `propagation_chain`
- `execution_plan_summary`
- `lock_wait_graph`
- `sql_pattern_clusters`
- `aggregate_invariants`
- `domain_constraint_checks`

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "log or database or domain"
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/log_analysis backend/app/services/db_analysis backend/app/services/domain_analysis backend/app/services/tool_context/focused_context.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: deepen log database and domain agents"
```

### Task 7: Add Long-Running Debate State and Convergence Logic

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/phase_executor.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`

**Step 1: Write the failing test**

覆盖：
- follow-up command
- evidence coverage
- top-k hypotheses
- debate stability score
- convergence stop condition

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py -q -k "followup or coverage or top_k or convergence"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

新增状态字段：
- `top_k_hypotheses`
- `evidence_coverage`
- `round_objectives`
- `round_gap_summary`
- `debate_stability_score`

主 Agent 支持：
- 二次追问
- Critic/Rebuttal 插入
- 动态停止

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/runtime/langgraph/state.py backend/app/runtime/langgraph_runtime.py backend/app/runtime/langgraph/nodes/supervisor.py backend/app/runtime/langgraph/phase_executor.py backend/tests/test_runtime_message_flow.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: add long-running debate convergence logic"
```

### Task 8: Make Debate Depth Configurable and Wire UI Settings

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/config.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/services/api.ts`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Settings/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`

**Step 1: Write the failing test**

覆盖：
- `quick / standard / deep` 模式
- `max_rounds` 可配置
- `deep` 模式默认多轮

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py -q -k "depth mode or max_rounds"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

新增：
- `analysis_depth_mode`
- `default_max_rounds_by_mode`

并在设置页接入。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py -q
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/config.py backend/app/runtime/langgraph_runtime.py frontend/src/services/api.ts frontend/src/pages/Settings/index.tsx backend/tests/test_runtime_message_flow.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: add configurable debate depth mode"
```

### Task 9: Upgrade Frontend Process and Result Visualization

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DialogueStream.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/AgentNetworkGraph.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateResultPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`

**Step 1: Write the failing test**

验证：
- 多轮分组
- 主 Agent 追问链
- 证据引用卡
- Top-K 根因
- 证据覆盖

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- FAIL，直到新结构完成接线

**Step 3: Write minimal implementation**

补过程页和结果页：
- 多轮展示
- 追问链
- Top-K 根因
- 因果链和覆盖图

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add frontend/src/pages/Incident/index.tsx frontend/src/components/incident/DebateProcessPanel.tsx frontend/src/components/incident/DialogueStream.tsx frontend/src/components/incident/AgentNetworkGraph.tsx frontend/src/components/incident/DebateResultPanel.tsx frontend/src/styles/global.css
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: visualize long-running debate and evidence"
```

### Task 10: Full Regression, Smoke, and Documentation Sync

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/wiki/code_wiki_v2.md`
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/agents/agent-catalog.md`
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/agents/protocol-contracts.md`
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/agents/tooling-and-audit.md`

**Step 1: Run backend regression**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/test_runtime_message_flow.py \
  backend/tests/test_graph_builder.py \
  backend/tests/test_agent_tool_context_service.py \
  backend/tests/test_agent_tool_audit.py \
  backend/tests/test_agent_depth_contracts.py -q
```

Expected:
- PASS

**Step 2: Run frontend build**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- PASS

**Step 3: Run smoke**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && SMOKE_SCENARIO=order-502-db-lock node ./scripts/smoke-e2e.mjs
```

Expected:
- 多轮分析完整完成
- 不长期 pending
- 日志可见 follow-up / convergence 轨迹

**Step 4: Update docs**

同步：
- 新模块结构
- 新 Agent 深度能力
- 新长程辩论机制
- 新前端展示能力

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend frontend docs
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: unify architecture cleanup and analysis depth upgrade"
```

## Acceptance Criteria

1. `langgraph_runtime.py` 与 `agent_tool_context_service.py` 明显瘦身，职责清晰。
2. `CodeAgent` 能输出代码闭包，不再只停留在轻量方法摘要。
3. `LogAgent` 能输出统一时序传播链。
4. `DatabaseAgent` 能输出锁等待图、执行计划和 SQL 模式聚类摘要。
5. `DomainAgent` 能输出领域约束检查。
6. 主 Agent 支持多轮追问与动态收敛。
7. 前端能展示多轮辩论、证据链、Top-K 根因和覆盖图。
8. quick 模式和现有主契约保持兼容。

## Risk Control

1. 所有步骤先补失败测试，再迁移实现。
2. 先做架构基础，再做深度增强，避免重复搬运代码。
3. 前端展示最后接入，避免后端结构未稳定时 UI 频繁返工。
4. 每阶段都跑局部回归，最后再跑 smoke。
