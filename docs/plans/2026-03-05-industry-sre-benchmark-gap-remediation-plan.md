# Industry SRE Benchmark Gap Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前 RCA 多 Agent 系统从“可用”提升到“业界对标版”，补齐并行协作、真实数据源接入深度、证据推理与治理闭环能力。  
**Architecture:** 保持现有 LangGraph 主架构不变，优先做“状态流转标准化 + 并行执行真实化 + 连接器平台化 + 结论质量门禁强化”。所有持久化继续使用本地文件或本地 SQLite，不引入外部数据库。  
**Tech Stack:** FastAPI, LangGraph, LangChain/OpenAI-compatible API, React + Ant Design, Pytest, GitHub Actions。

---

### Task 1: 真正并行化分析 Agent 调度（替代伪并行）

**Files:**
- Modify: `backend/app/runtime/langgraph/nodes/agent_subgraph.py`
- Modify: `backend/app/runtime/langgraph/builder.py`
- Modify: `backend/app/runtime/langgraph/state.py`
- Test: `backend/tests/test_langgraph_parallel_dispatch.py`

**Step 1: Write the failing test**
```python
def test_analysis_parallel_returns_send_objects():
    state = {"next_step": "analysis_parallel", "agent_commands": {"LogAgent": {}, "CodeAgent": {}}}
    sends = route_to_parallel_agents(state)
    assert isinstance(sends, list)
    assert len(sends) == 2
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_langgraph_parallel_dispatch.py -k send`  
Expected: FAIL（当前返回 `analysis_parallel_node` 字符串）

**Step 3: Write minimal implementation**
- 在 `route_to_parallel_agents` 返回 `Send(...)` 列表。
- 每个并行 Agent 只携带必要上下文（messages/routing_state/output_state 精简字段）。
- 合并器节点统一回收并更新 state。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_langgraph_parallel_dispatch.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/runtime/langgraph/nodes/agent_subgraph.py backend/app/runtime/langgraph/builder.py backend/app/runtime/langgraph/state.py backend/tests/test_langgraph_parallel_dispatch.py
git commit -m "feat(runtime): enable true parallel agent dispatch with LangGraph Send"
```

### Task 2: 消息流转统一到 `MessagesState`（减少手工 JSON 拼接）

**Files:**
- Modify: `backend/app/runtime/langgraph/prompts.py`
- Modify: `backend/app/runtime/langgraph/context_builders.py`
- Modify: `backend/app/runtime/langgraph/execution.py`
- Test: `backend/tests/test_message_state_prompt_minify.py`

**Step 1: Write the failing test**
```python
def test_prompt_uses_messages_not_history_cards_dump():
    prompt = build_agent_prompt(...)
    assert "已有观点卡片" not in prompt
    assert "最近对话消息" in prompt
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_message_state_prompt_minify.py`  
Expected: FAIL（当前仍拼接 history_cards JSON）

**Step 3: Write minimal implementation**
- Prompt 仅消费最近 `messages` + `agent_mailbox` 的摘要。
- 删除大段 `history_cards` 序列化拼接。
- 保留必须结构化字段：命令、未决问题、最近证据摘要。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_message_state_prompt_minify.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/runtime/langgraph/prompts.py backend/app/runtime/langgraph/context_builders.py backend/app/runtime/langgraph/execution.py backend/tests/test_message_state_prompt_minify.py
git commit -m "refactor(runtime): unify prompt context on MessagesState flow"
```

### Task 3: 连接器生产化增强（Telemetry/CMDB/Prometheus/Loki）

**Files:**
- Modify: `backend/app/runtime/connectors/http_utils.py`
- Modify: `backend/app/runtime/connectors/telemetry_connector.py`
- Modify: `backend/app/runtime/connectors/cmdb_connector.py`
- Modify: `backend/app/runtime/connectors/prometheus_connector.py`
- Modify: `backend/app/services/agent_tool_context_service.py`
- Test: `backend/tests/test_connectors_http_observability.py`

**Step 1: Write the failing test**
```python
def test_connector_returns_http_trace_fields():
    payload = await connector.fetch(cfg, ctx)
    assert "request_meta" in payload
    assert "latency_ms" in payload.get("request_meta", {})
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_connectors_http_observability.py`  
Expected: FAIL

**Step 3: Write minimal implementation**
- 统一 `http_get_json` 返回：`status_code/latency_ms/url/method/retry_count/error`。
- Agent 工具审计中写入连接器 HTTP 入参与摘要回参（脱敏后）。
- connector `enabled=true` 且 endpoint 不可用时，明确 `status=degraded`，不阻塞主流程。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_connectors_http_observability.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/runtime/connectors/http_utils.py backend/app/runtime/connectors/telemetry_connector.py backend/app/runtime/connectors/cmdb_connector.py backend/app/runtime/connectors/prometheus_connector.py backend/app/services/agent_tool_context_service.py backend/tests/test_connectors_http_observability.py
git commit -m "feat(connectors): add request tracing and degraded-mode behavior"
```

### Task 4: Pending 防卡死与会话看门狗

**Files:**
- Modify: `backend/app/services/debate_service.py`
- Modify: `backend/app/runtime/task_registry.py`
- Modify: `backend/app/api/incidents.py`
- Test: `backend/tests/test_pending_watchdog.py`

**Step 1: Write the failing test**
```python
def test_session_exits_pending_when_llm_stalls():
    result = run_timeout_case(...)
    assert result["status"] in {"failed", "closed", "degraded"}
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_pending_watchdog.py`  
Expected: FAIL（可能长期 pending）

**Step 3: Write minimal implementation**
- 增加 session watchdog：超过预算自动触发降级收敛（JudgeAgent fallback）。
- 写入终止原因与最后进展事件，前端可感知“已超时降级结束”。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_pending_watchdog.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/debate_service.py backend/app/runtime/task_registry.py backend/app/api/incidents.py backend/tests/test_pending_watchdog.py
git commit -m "fix(runtime): add watchdog to prevent long pending sessions"
```

### Task 5: 前端战情与调查页体验对齐（非空白、首证据可见）

**Files:**
- Modify: `frontend/src/pages/WarRoom/index.tsx`
- Modify: `frontend/src/pages/Incident/index.tsx`
- Modify: `frontend/src/components/incident/DebateProcessPanel.tsx`
- Modify: `frontend/src/components/incident/DebateResultPanel.tsx`
- Test: `frontend/src/__tests__/incident-flow.spec.tsx`

**Step 1: Write the failing test**
```tsx
it('shows friendly hint before first evidence arrives', async () => {
  render(<WarRoomPage />);
  expect(screen.getByText(/等待首批证据/)).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**
Run: `cd frontend && npm run test -- incident-flow`  
Expected: FAIL

**Step 3: Write minimal implementation**
- 战情页增加 `first_evidence_at` SLA 提示（10 秒目标）。
- 调查页无数据时展示可执行指引，不出现空白区。
- 工具调用与时间线保持同源事件排序（北京时间）。

**Step 4: Run test to verify it passes**
Run: `cd frontend && npm run typecheck && npm run build`  
Expected: PASS

**Step 5: Commit**
```bash
git add frontend/src/pages/WarRoom/index.tsx frontend/src/pages/Incident/index.tsx frontend/src/components/incident/DebateProcessPanel.tsx frontend/src/components/incident/DebateResultPanel.tsx frontend/src/__tests__/incident-flow.spec.tsx
git commit -m "feat(frontend): improve war-room and incident UX for first-evidence visibility"
```

### Task 6: 因果推理层 v2（依赖拓扑 + 证据传播）

**Files:**
- Modify: `backend/app/runtime/judgement/topology_reasoner.py`
- Modify: `backend/app/runtime/judgement/causal_score.py`
- Modify: `backend/app/services/debate_service.py`
- Test: `backend/tests/test_causal_topology_v2.py`

**Step 1: Write the failing test**
```python
def test_topology_score_penalizes_unlinked_evidence():
    score = score_topology_propagation(context=ctx, evidence=evidence)
    assert score["topology_score"] < 0.5
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_causal_topology_v2.py`  
Expected: FAIL

**Step 3: Write minimal implementation**
- 从接口映射构建 service->domain->aggregate->team 的路径评分。
- 证据未命中拓扑链路时降权，并输出冲突点/不确定性来源。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_causal_topology_v2.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/runtime/judgement/topology_reasoner.py backend/app/runtime/judgement/causal_score.py backend/app/services/debate_service.py backend/tests/test_causal_topology_v2.py
git commit -m "feat(judgement): implement topology-aware causal scoring v2"
```

### Task 7: 结论质量硬门禁（禁止空结论/模糊结论）

**Files:**
- Modify: `backend/app/services/debate_service.py`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/app/runtime/langgraph/routing/rules_impl.py`
- Test: `backend/tests/test_no_empty_conclusion_gate.py`

**Step 1: Write the failing test**
```python
def test_report_generation_blocked_on_empty_conclusion():
    with pytest.raises(ValueError):
        generate_report_with_empty_root_cause(...)
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_no_empty_conclusion_gate.py`  
Expected: FAIL

**Step 3: Write minimal implementation**
- 若无有效 LLM 结论，禁止输出“需要进一步分析”作为最终报告。
- 强制输出：失败原因 + 缺失证据清单 + 下一步采证动作。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_no_empty_conclusion_gate.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/debate_service.py backend/app/services/report_service.py backend/app/runtime/langgraph/routing/rules_impl.py backend/tests/test_no_empty_conclusion_gate.py
git commit -m "fix(quality-gate): block empty conclusions and enforce actionable fallback"
```

### Task 8: 外部协同从“模板”升级为“适配器入口”

**Files:**
- Modify: `backend/app/services/governance_ops_service.py`
- Create: `backend/app/runtime_ext/integrations/base_adapter.py`
- Create: `backend/app/runtime_ext/integrations/jira_adapter.py`
- Create: `backend/app/runtime_ext/integrations/pagerduty_adapter.py`
- Test: `backend/tests/test_external_sync_adapters.py`

**Step 1: Write the failing test**
```python
def test_jira_adapter_dry_run_generates_request_payload():
    payload = adapter.build_create_issue(...)
    assert "fields" in payload
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_external_sync_adapters.py`  
Expected: FAIL

**Step 3: Write minimal implementation**
- 先实现 dry-run 适配器（不对外发请求），仅产出标准请求体。
- 保留本地文件审计；后续可通过开关启用真实调用。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_external_sync_adapters.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/governance_ops_service.py backend/app/runtime_ext/integrations/base_adapter.py backend/app/runtime_ext/integrations/jira_adapter.py backend/app/runtime_ext/integrations/pagerduty_adapter.py backend/tests/test_external_sync_adapters.py
git commit -m "feat(integrations): add adapter entrypoints for external sync providers"
```

### Task 9: 治理能力强化（租户配额 + 运行时预算执行）

**Files:**
- Modify: `backend/app/services/governance_ops_service.py`
- Modify: `backend/app/services/debate_service.py`
- Modify: `backend/app/runtime/langgraph/execution.py`
- Test: `backend/tests/test_tenant_quota_budget_enforcement.py`

**Step 1: Write the failing test**
```python
def test_tenant_quota_blocks_new_session_when_limit_reached():
    with pytest.raises(PermissionError):
        create_session_for_tenant("team-a")
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_tenant_quota_budget_enforcement.py`  
Expected: FAIL

**Step 3: Write minimal implementation**
- 会话创建与执行前检查租户并发额度/日额度/token预算。
- 超限返回可解释错误，并记录治理审计事件。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_tenant_quota_budget_enforcement.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/governance_ops_service.py backend/app/services/debate_service.py backend/app/runtime/langgraph/execution.py backend/tests/test_tenant_quota_budget_enforcement.py
git commit -m "feat(governance): enforce tenant quota and runtime budget gates"
```

### Task 10: 收敛冗余实现（AgentFactory 与主执行路径）

**Files:**
- Modify: `backend/app/runtime/agents/factory.py`
- Modify: `backend/app/runtime/langgraph/execution.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_agent_factory_runtime_path.py`

**Step 1: Write the failing test**
```python
def test_runtime_path_matches_factory_toggle():
    assert resolve_runtime_mode(use_factory=True) == "factory"
```

**Step 2: Run test to verify it fails**
Run: `pytest -q backend/tests/test_agent_factory_runtime_path.py`  
Expected: FAIL

**Step 3: Write minimal implementation**
- 明确两种路径二选一：`AGENT_USE_FACTORY=true` 走 factory；否则删除未使用分支。
- 在日志中打印最终生效路径，避免“配置形同虚设”。

**Step 4: Run test to verify it passes**
Run: `pytest -q backend/tests/test_agent_factory_runtime_path.py`  
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/runtime/agents/factory.py backend/app/runtime/langgraph/execution.py backend/app/config.py backend/tests/test_agent_factory_runtime_path.py
git commit -m "refactor(runtime): align agent factory path with runtime execution path"
```

## Global Verification

1. Backend tests: `pytest -q backend/tests`  
2. Frontend: `cd frontend && npm run typecheck && npm run build`  
3. E2E smoke:
   - `FRONTEND_URL=http://127.0.0.1:5173 BACKEND_URL=http://127.0.0.1:8000 SMOKE_SCENARIO=order-502-db-lock node ./scripts/smoke-e2e.mjs`
   - `FRONTEND_URL=http://127.0.0.1:5173 BACKEND_URL=http://127.0.0.1:8000 SMOKE_SCENARIO=order-404-route-miss node ./scripts/smoke-e2e.mjs`
4. Benchmark gate:
   - `cd backend && python -m app.benchmark.cli --limit 5 --timeout 240`
   - `python scripts/benchmark-gate.py --min-top1 0.30 --min-top3 0.45 --max-timeout 0.50 --max-empty 0.40 --max-first-evidence-p95-ms 10000`

## Acceptance Criteria

1. 首批证据在 10 秒内可见（战情页可观测）。  
2. 不再出现长期 `pending` 会话。  
3. 最终报告不允许“空根因/纯占位结论”。  
4. Top-K 与证据链可解释度提升（含冲突/不确定性标注）。  
5. 工具调用具备可追溯 HTTP/文件/Git 审计记录。  
6. CI Benchmark Gate 能阻断明显回归。  

