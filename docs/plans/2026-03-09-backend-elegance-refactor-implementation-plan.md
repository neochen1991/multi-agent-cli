# Backend Elegance Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不改变现有产品能力和前端交互的前提下，重构后端主链路，降低上帝类复杂度，提高模块边界清晰度、测试可维护性和代码可读性。

**Architecture:** 以“编排器瘦身 + 领域服务下沉 + 明确状态转换边界”为主线，对运行时编排层和工具上下文层做分层拆分。保留现有 LangGraph 主流程与 API 契约，优先抽离纯函数、策略对象和上下文构建器，使 Orchestrator 仅负责协调，AgentToolContextService 仅负责路由。

**Tech Stack:** Python 3.14, FastAPI, LangGraph, LangChain Core, pytest, structlog

---

## Scope

- 仅覆盖后端主链路：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
  - 直接依赖的运行时模块与测试
- 不改变前端页面结构
- 不引入外部数据库或新的基础设施
- 保持现有 API、WebSocket 事件名、分析流程主行为兼容

## Non-Goals

- 不重写整套 LangGraph 图结构
- 不替换现有 LLM SDK 路径
- 不做新的业务功能扩展
- 不处理前端 V1/V2 页面重构

## Current Problems

1. `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py` 体积过大，混合了：
   - runtime policy
   - prompt compaction
   - state projection
   - message/mailbox 操作
   - agent context 组装
   - event emission
   - timeout/budget 规则
2. `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py` 既做路由，又做：
   - git 访问
   - 文件搜索
   - PG 查询
   - 日志读取
   - focused context 汇总
   - tool audit 记录
3. 测试覆盖虽然存在，但较多依赖私有方法，导致重构阻力大。
4. 很多逻辑已经具备“模式雏形”，但仍堆积在单文件中，缺少明确的模块边界。

## Target Design

### 1. Runtime 层目标结构

将当前 orchestrator 收敛为“协调层”，下沉实现细节到以下模块：

- `backend/app/runtime/langgraph/runtime_policy.py`
  - execution mode / deployment profile / budget 规则
- `backend/app/runtime/langgraph/context_facade.py`
  - orchestrator 对外的上下文构建门面
- `backend/app/runtime/langgraph/state_views.py`
  - history cards、dialogue items、routing round cards 等状态投影视图
- `backend/app/runtime/langgraph/budgeting.py`
  - max_tokens / queue_timeout / http_timeout / timeout_plan 规则
- `backend/app/runtime/langgraph/event_payloads.py`
  - 统一构建 WS / audit / report 事件载荷

Orchestrator 仅保留：
- session 生命周期
- graph compile/run
- service 组装
- 跨服务协调入口

### 2. Tool Context 层目标结构

将当前 AgentToolContextService 拆为“路由器 + 若干 provider + focused context assembler”：

- `backend/app/services/tool_context/router.py`
  - 按 agent_name 分发
- `backend/app/services/tool_context/providers/code_provider.py`
- `backend/app/services/tool_context/providers/log_provider.py`
- `backend/app/services/tool_context/providers/domain_provider.py`
- `backend/app/services/tool_context/providers/database_provider.py`
- `backend/app/services/tool_context/providers/metrics_provider.py`
- `backend/app/services/tool_context/providers/change_provider.py`
- `backend/app/services/tool_context/providers/runbook_provider.py`
- `backend/app/services/tool_context/focused_context.py`
  - 统一构建各 Agent 的 focused_context / summary
- `backend/app/services/tool_context/audit.py`
  - 审计日志、request/response summary、execution path 组装

保留对外门面：
- `AgentToolContextService.build_context(...)`
- `AgentToolContextService.build_focused_context(...)`

### 3. 测试层目标结构

重构测试以贴近模块边界：

- `backend/tests/runtime/test_runtime_policy.py`
- `backend/tests/runtime/test_budgeting.py`
- `backend/tests/runtime/test_state_views.py`
- `backend/tests/services/tool_context/test_code_provider.py`
- `backend/tests/services/tool_context/test_log_provider.py`
- `backend/tests/services/tool_context/test_focused_context.py`

保留现有高价值回归测试：
- `backend/tests/test_runtime_message_flow.py`
- `backend/tests/test_graph_builder.py`
- `backend/tests/test_agent_tool_context_service.py`

---

### Task 1: Freeze Runtime Contracts Before Refactor

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_graph_builder.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_runtime_contracts.py`

**Step 1: Write the failing tests**

补 3 类契约测试：
- orchestrator 暴露的关键 helper 仍返回相同 shape
- quick/background 模式预算规则不回退
- supervisor / agent node 对 state 增量字段保持兼容

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/runtime/test_runtime_contracts.py -q
```

Expected:
- 新增测试失败，因为契约测试文件尚不存在或断言未满足

**Step 3: Write minimal implementation**

仅补测试文件，不改运行时代码。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/runtime/test_runtime_contracts.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/tests/runtime/test_runtime_contracts.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "test: freeze runtime refactor contracts"
```

### Task 2: Extract Runtime Policy and Budget Strategy

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/runtime_policy.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/budgeting.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_runtime_policy.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_budgeting.py`

**Step 1: Write the failing test**

为以下纯规则写测试：
- execution mode -> collaboration/critique/verification flags
- first round / expert opening window 判定
- agent max tokens / timeout_plan / queue timeout / http timeout

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/runtime/test_runtime_policy.py backend/tests/runtime/test_budgeting.py -q
```

Expected:
- FAIL，因为模块尚未创建

**Step 3: Write minimal implementation**

把下面逻辑从 orchestrator 下沉到独立类或纯函数：
- `_configure_runtime_policy`
- `_is_fast_execution_mode`
- `_is_fast_first_round`
- `_has_expert_turns`
- `_is_fast_analysis_opening`
- `_agent_max_tokens`
- `_agent_timeout_plan`
- `_agent_queue_timeout`
- `_agent_http_timeout`

Orchestrator 改成组合调用，不再持有细节实现。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/runtime/test_runtime_policy.py backend/tests/runtime/test_budgeting.py backend/tests/test_runtime_message_flow.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/runtime/langgraph/runtime_policy.py backend/app/runtime/langgraph/budgeting.py backend/app/runtime/langgraph_runtime.py backend/tests/runtime/test_runtime_policy.py backend/tests/runtime/test_budgeting.py backend/tests/test_runtime_message_flow.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: extract runtime policy and budgeting"
```

### Task 3: Extract Runtime State Views and Message Projections

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state_views.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_state_views.py`

**Step 1: Write the failing test**

覆盖：
- `_history_cards_for_state`
- `_round_cards_for_routing`
- `_dialogue_items_from_messages`
- `_messages_to_cards`
- `_message_deltas_from_cards`

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/runtime/test_state_views.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

把状态投影和 message/card 视图转换下沉到独立模块；orchestrator 只保留轻量包装方法以兼容现有调用点。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/runtime/test_state_views.py backend/tests/test_runtime_message_flow.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/runtime/langgraph/state_views.py backend/app/runtime/langgraph_runtime.py backend/tests/runtime/test_state_views.py backend/tests/test_runtime_message_flow.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: extract runtime state views"
```

### Task 4: Split Tool Context Into Router and Providers

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/router.py`
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

为不同 agent 的 provider 路由写测试：
- `CodeAgent` -> code provider
- `LogAgent` -> log provider
- `ProblemAnalysisAgent` / `JudgeAgent` -> rule suggestion provider
- `DatabaseAgent` -> database provider

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/services/tool_context/test_router.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

把 `build_context` 里的大分支迁移到 router + provider 注册表，不改变外部返回结构。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/services/tool_context/test_router.py backend/tests/test_agent_tool_context_service.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/tool_context/router.py backend/app/services/tool_context/providers backend/app/services/agent_tool_context_service.py backend/tests/services/tool_context/test_router.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: split tool context router and providers"
```

### Task 5: Extract Focused Context Assembly

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/focused_context.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/services/tool_context/test_focused_context.py`

**Step 1: Write the failing test**

为以下 focused context 输出写独立测试：
- `CodeAgent`
- `LogAgent`
- `DatabaseAgent`
- `MetricsAgent`
- `DomainAgent`
- `RunbookAgent`
- `ProblemAnalysisAgent`
- `JudgeAgent`

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/services/tool_context/test_focused_context.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

将 `build_focused_context` 及相关 `_build_*_focused_context` 迁移为纯函数或 assembler 类；service 仅负责注入输入和选择 assembler。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/services/tool_context/test_focused_context.py backend/tests/test_agent_tool_context_service.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/tool_context/focused_context.py backend/app/services/agent_tool_context_service.py backend/tests/services/tool_context/test_focused_context.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: extract focused context assembly"
```

### Task 6: Extract Tool Audit and Execution Path Assembly

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/services/tool_context/audit.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_agent_tool_audit.py`

**Step 1: Write the failing test**

覆盖：
- command gate summary
- request/response summary shape
- execution path
- permission decision

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_audit.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

提取 audit entry builder，避免 provider 内部散落拼字典。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/test_agent_tool_audit.py backend/tests/test_agent_tool_context_service.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/services/tool_context/audit.py backend/app/services/agent_tool_context_service.py backend/tests/test_agent_tool_audit.py backend/tests/test_agent_tool_context_service.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: extract tool audit assembly"
```

### Task 7: Slim Orchestrator Public Surface

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/agents.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`
- Create: `/Users/neochen/multi-agent-cli_v2/backend/tests/runtime/test_orchestrator_surface.py`

**Step 1: Write the failing test**

定义 orchestrator 最终保留的公开协作面：
- graph run lifecycle
- emit helpers
- record helpers
- service facade properties

**Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/runtime/test_orchestrator_surface.py -q
```

Expected:
- FAIL

**Step 3: Write minimal implementation**

将节点层对 orchestrator 的调用收口到少量 facade 方法，减少节点直接依赖 orchestrator 私有细节。

**Step 4: Run test to verify it passes**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests/runtime/test_orchestrator_surface.py backend/tests/test_graph_builder.py backend/tests/test_runtime_message_flow.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/runtime/langgraph_runtime.py backend/app/runtime/langgraph/nodes/agents.py backend/app/runtime/langgraph/nodes/supervisor.py backend/tests/runtime/test_orchestrator_surface.py backend/tests/test_graph_builder.py backend/tests/test_runtime_message_flow.py
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: slim orchestrator public surface"
```

### Task 8: Regression Suite and Readability Cleanup

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/agents/agent-catalog.md`
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/agents/tooling-and-audit.md`
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/wiki/code_wiki_v2.md`

**Step 1: Run full targeted regression**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && \
backend/.venv/bin/pytest \
  backend/tests/test_runtime_message_flow.py \
  backend/tests/test_graph_builder.py \
  backend/tests/test_agent_tool_context_service.py \
  backend/tests/test_agent_tool_audit.py \
  backend/tests/test_debate_service_error_classification.py \
  backend/tests/test_p0_incident_debate_report.py -q
```

Expected:
- PASS

**Step 2: Run smoke verification**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && SMOKE_SCENARIO=order-502-db-lock node ./scripts/smoke-e2e.mjs
```

Expected:
- 完成真实 incident 分析，不能长期 pending

**Step 3: Cleanup comments and docs**

- 删除重构后多余包装注释
- 更新代码 wiki 与 Agent tooling 文档，反映新模块结构

**Step 4: Run final verification**

Run:
```bash
cd /Users/neochen/multi-agent-cli_v2 && backend/.venv/bin/pytest backend/tests -q
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run -s build
```

Expected:
- 后端测试通过
- 前端构建通过

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add backend/app/runtime backend/app/services/tool_context backend/app/services/agent_tool_context_service.py backend/tests docs/agents docs/wiki/code_wiki_v2.md
git -C /Users/neochen/multi-agent-cli_v2 commit -m "refactor: improve backend readability and modularity"
```

## Acceptance Criteria

1. `langgraph_runtime.py` 明显瘦身，职责聚焦在协调与生命周期。
2. `agent_tool_context_service.py` 不再承载 provider 细节与 focused context 细节。
3. 核心规则具备独立单元测试，不依赖大型 orchestrator 集成测试才能验证。
4. 现有 WebSocket 事件、报告生成、工具审计输出 shape 不发生破坏性变化。
5. 至少一条真实 smoke 场景完成，且不出现长期 pending。

## Risk Controls

1. 每个 Task 都先补失败测试，再迁移代码。
2. 每个 Task 完成后运行局部回归，避免一次性大爆炸式重构。
3. 对外接口保持 facade，不在第一轮重构时推翻现有调用点。
4. 若 smoke 出现回归，优先回退最近一个 Task，而不是继续叠加修复。

## Suggested Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8

## Notes

- 当前工作区已存在未提交改动：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py` 与 `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`。实施时必须在这些改动基础上继续，不得覆盖或回滚。
- 本计划优先做“可维护性重构”，不是功能性扩展。

---

Plan complete and saved to `/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-09-backend-elegance-refactor-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
