# Analysis Depth Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不破坏现有功能契约的前提下，提升多 Agent 系统的分析深度、长程辩论能力和前端证据可视化能力。

**Architecture:** 保留现有 LangGraph 主体，沿着“Agent 深度上下文增强 + 多轮追问收敛 + 前端证据展示升级”的路线演进。兼容当前 quick 模式和既有 API / WebSocket 契约，优先用结构化状态和 focused context 增强推理深度。

**Tech Stack:** Python 3.14, FastAPI, LangGraph, LangChain Core, pytest, React, TypeScript

---

### Task 1: Freeze Current Contracts Before Depth Upgrade

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_context_service.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_depth_contracts.py`

**Step 1: Write the failing test**

补契约测试，冻结：
- `agent_tool_context_prepared` 事件 shape
- `focused_context` 主要字段 shape
- 主 Agent / 专家 Agent / JudgeAgent 输出结构不退化

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_depth_contracts.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

新增测试文件，不改生产代码。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_depth_contracts.py backend/tests/test_runtime_message_flow.py backend/tests/test_agent_tool_context_service.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/tests/test_agent_depth_contracts.py backend/tests/test_runtime_message_flow.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "test: freeze analysis depth contracts"
```

### Task 2: Upgrade CodeAgent to Topology Closure Analysis

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/code_analysis/source_loader.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/code_analysis/symbol_resolver.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/code_analysis/call_graph_builder.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_context_service.py`

**Step 1: Write the failing test**

覆盖：
- `controller -> service -> dao`
- SQL 绑定
- downstream rpc/client 绑定
- transaction / pool / retry 风险点提取

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "code"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

将 `CodeAgent` focused context 升级为：
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
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/code_analysis backend/app/services/agent_tool_context_service.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: deepen code agent topology closure analysis"
```

### Task 3: Upgrade LogAgent to Unified Timeline Alignment

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/log_analysis/timeline_extractor.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/log_analysis/trace_alignment.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_context_service.py`

**Step 1: Write the failing test**

覆盖：
- trace_id / span_id / instance 对齐
- metric marker 与日志事件对齐
- propagation chain 生成

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "log"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

`LogAgent` focused context 增加：
- `trace_timeline`
- `instance_scope`
- `aligned_metric_markers`
- `propagation_chain`

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "log"
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/log_analysis backend/app/services/agent_tool_context_service.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: align log agent timeline with trace and metrics"
```

### Task 4: Upgrade DatabaseAgent to Execution and Lock Graph Analysis

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/db_analysis/execution_plan_summary.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/db_analysis/lock_wait_graph.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/db_analysis/sql_pattern_cluster.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_context_service.py`

**Step 1: Write the failing test**

覆盖：
- execution plan summary
- lock wait graph
- blocker/waiter chain
- SQL 模式聚类
- db root cause assessment

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "database"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

`DatabaseAgent` focused context 增加：
- `execution_plan_summary`
- `lock_wait_graph`
- `blocking_chain`
- `sql_pattern_clusters`
- `db_root_cause_assessment`

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "database"
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/db_analysis backend/app/services/agent_tool_context_service.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: deepen database agent lock and plan analysis"
```

### Task 5: Upgrade DomainAgent to Constraint Reasoning

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/domain_analysis/constraint_checks.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_context_service.py`

**Step 1: Write the failing test**

覆盖：
- aggregate invariants
- domain constraint checks
- transaction order constraints
- violation hypotheses

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "domain"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

`DomainAgent` focused context 增加：
- `aggregate_invariants`
- `domain_constraint_checks`
- `transaction_order_constraints`
- `domain_violation_hypotheses`

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_context_service.py -q -k "domain"
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/domain_analysis backend/app/services/agent_tool_context_service.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: add domain constraint reasoning for domain agent"
```

### Task 6: Introduce Long-Running Debate Mechanics

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/phase_executor.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`

**Step 1: Write the failing test**

覆盖：
- 主 Agent 二次追问
- 多轮追问的 gap tracking
- evidence coverage tracking
- top-k hypothesis tracking
- convergence stop condition

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py -q -k "followup or coverage or top_k or convergence"
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

新增运行时状态：
- `top_k_hypotheses`
- `evidence_coverage`
- `round_objectives`
- `round_gap_summary`
- `debate_stability_score`

主 Agent 增加：
- follow-up dispatch
- 冲突识别后触发 Critic/Rebuttal
- 动态停止判定

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/runtime/langgraph_runtime.py backend/app/runtime/langgraph/nodes/supervisor.py backend/app/runtime/langgraph/phase_executor.py backend/app/runtime/langgraph/state.py backend/tests/test_runtime_message_flow.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: add long-running debate and convergence controls"
```

### Task 7: Make Debate Depth Configurable

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/config.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Settings/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/services/api.ts`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`

**Step 1: Write the failing test**

覆盖：
- `quick/standard/deep` 三种深度模式
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

新增配置：
- `analysis_depth_mode`
- `default_max_rounds_by_mode`

前端设置页增加深度模式入口。

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
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/config.py backend/app/runtime/langgraph_runtime.py frontend/src/pages/Settings/index.tsx frontend/src/services/api.ts backend/tests/test_runtime_message_flow.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: add configurable debate depth modes"
```

### Task 8: Frontend Multi-Round Process Visualization

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DialogueStream.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/AgentNetworkGraph.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`

**Step 1: Write the failing test**

新增前端逻辑验证：
- 多轮对话分组
- 主 Agent 追问链
- Critic/Rebuttal 插入展示
- 证据引用卡

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- 构建或类型检查失败，直到新数据结构和展示逻辑补齐

**Step 3: Write minimal implementation**

辩论过程页新增：
- 多轮分组
- 追问关系
- 证据引用卡
- round objective / gap summary 展示

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add frontend/src/pages/Incident/index.tsx frontend/src/components/incident/DebateProcessPanel.tsx frontend/src/components/incident/DialogueStream.tsx frontend/src/components/incident/AgentNetworkGraph.tsx frontend/src/styles/global.css
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: visualize multi-round debate process"
```

### Task 9: Frontend Evidence and Top-K Visualization

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateResultPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`

**Step 1: Write the failing test**

验证页面可消费：
- `top_k_hypotheses`
- `evidence_coverage`
- `propagation_chain`
- `lock_wait_graph`
- `call_graph_summary`

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- FAIL，直到新字段完成展示

**Step 3: Write minimal implementation**

结果页新增：
- Top-K 根因卡片
- 证据覆盖图
- 因果链摘要
- 验证与反证说明

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add frontend/src/components/incident/DebateResultPanel.tsx frontend/src/pages/Incident/index.tsx frontend/src/styles/global.css
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: add evidence and top-k result visualization"
```

### Task 10: Full Regression and Smoke Verification

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/wiki/code_wiki_v2.md`
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/agents/agent-catalog.md`
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/agents/protocol-contracts.md`

**Step 1: Run targeted backend regression**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/test_runtime_message_flow.py \
  backend/tests/test_agent_tool_context_service.py \
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

**Step 3: Run real smoke**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && SMOKE_SCENARIO=order-502-db-lock node ./scripts/smoke-e2e.mjs
```

Expected:
- 多 Agent 流程完成
- 不长期 pending
- 日志中可见多轮追问或收敛判定

**Step 4: Update docs**

同步更新：
- 新的 Agent 深度能力
- 多轮辩论收敛逻辑
- 前端新增证据展示能力

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend frontend docs
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: upgrade analysis depth across agents and ui"
```

## Acceptance Criteria

1. `CodeAgent` 输出完整代码闭包摘要，而非仅文件命中。
2. `LogAgent` 输出 trace/span/instance/metric 对齐后的传播链。
3. `DatabaseAgent` 输出执行计划、锁等待图和 SQL 模式聚类摘要。
4. `DomainAgent` 输出领域约束检查与不变量假设。
5. 主 Agent 支持多轮追问与收敛，不再局限于默认单轮。
6. 前端可清晰展示多轮对话、证据链、Top-K 根因和因果图。
7. quick 模式保持兼容，现有事件契约不破坏。

## Risks

1. 运行耗时上升
- 通过深度模式配置和停止条件控制

2. token 消耗上升
- 用结构化摘要代替无界文本堆积

3. 前端事件展示复杂度上升
- 保持旧事件兼容，新展示逐步增强
