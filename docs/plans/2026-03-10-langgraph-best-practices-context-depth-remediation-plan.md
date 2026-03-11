# LangGraph Best Practices, Agent Context, and Analysis Depth Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring the runtime closer to LangGraph best practices by hardening state boundaries, making agent-specific context explicit, and turning `analysis_depth_mode` into a real depth policy instead of mostly a round-count alias.

**Architecture:** Keep the existing `StateGraph` orchestration, but finish the migration to structured runtime state, introduce an explicit per-agent context envelope, and move depth decisions into runtime policy, prompting, and coverage scoring. Preserve current event contracts and replay compatibility while reducing prompt leakage and improving deep-analysis behavior.

**Tech Stack:** FastAPI, LangGraph, LangChain/OpenAI, Python typed state reducers, pytest, frontend TypeScript API contracts, repo-backed docs.

---

### Task 1: Normalize Runtime State Around Structured Views

**Files:**
- Modify: `backend/app/runtime/langgraph/state.py`
- Modify: `backend/app/runtime/langgraph/services/state_transition_service.py`
- Modify: `backend/app/runtime/langgraph/nodes/supervisor.py`
- Modify: `backend/app/runtime/langgraph/nodes/agents.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Test: `backend/tests/test_runtime_message_flow.py`
- Test: `backend/tests/test_graph_builder.py`
- Create: `backend/tests/runtime/test_structured_state_contract.py`

**Step 1: Write the failing test**

```python
def test_structured_state_snapshot_keeps_routing_phase_output_in_sync():
    state = create_initial_state({"title": "orders 502"}, max_rounds=2, max_discussion_steps=8)
    state["current_round"] = 2
    state["next_step"] = "speak:JudgeAgent"
    state["top_k_hypotheses"] = [{"agent_name": "LogAgent", "conclusion": "db lock"}]

    snapshot = structured_state_snapshot(state)

    assert snapshot["phase_state"]["current_round"] == 2
    assert snapshot["routing_state"]["next_step"] == "speak:JudgeAgent"
    assert snapshot["output_state"]["top_k_hypotheses"][0]["conclusion"] == "db lock"
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_structured_state_contract.py -q`
Expected: FAIL because state access still depends on mixed flat and structured reads in several paths.

**Step 3: Write minimal implementation**

Implement:
- a single authoritative read/write path for `phase_state`, `routing_state`, and `output_state`
- compatibility accessors for legacy flat fields
- a small helper used by nodes/runtime to read structured state first and emit synchronized snapshots last

Keep the existing public event/output contracts unchanged.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_structured_state_contract.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/state.py backend/app/runtime/langgraph/services/state_transition_service.py backend/app/runtime/langgraph/nodes/supervisor.py backend/app/runtime/langgraph/nodes/agents.py backend/app/runtime/langgraph_runtime.py backend/tests/runtime/test_structured_state_contract.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py
git commit -m "refactor: normalize structured langgraph state access"
```

### Task 2: Introduce an Explicit Agent Context Envelope

**Files:**
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Modify: `backend/app/services/agent_tool_context_service.py`
- Modify: `backend/app/runtime/langgraph/prompt_builder.py`
- Modify: `backend/app/runtime/langgraph/prompts.py`
- Modify: `backend/app/runtime/langgraph/phase_executor.py`
- Modify: `backend/app/runtime/langgraph/nodes/agents.py`
- Test: `backend/tests/test_agent_depth_contracts.py`
- Create: `backend/tests/runtime/test_agent_context_envelope.py`
- Docs: `docs/agents/protocol-contracts.md`
- Docs: `docs/wiki/code_wiki_v2.md`

**Step 1: Write the failing test**

```python
def test_agent_prompt_uses_context_envelope_without_dumping_full_incident():
    envelope = {
        "shared_context": {"incident_summary": {"title": "orders 502"}},
        "focused_context": {"target_tables": ["t_order"]},
        "tool_context": {"name": "db_snapshot_reader", "status": "ok"},
        "peer_context": [{"agent": "LogAgent", "summary": "lock wait"}],
        "mailbox_context": [{"sender": "ProblemAnalysisAgent", "message_type": "command"}],
    }

    prompt = build_peer_driven_prompt(
        spec=AgentSpec(name="DatabaseAgent", role="数据库专家", phase="analysis", system_prompt=""),
        loop_round=1,
        max_rounds=2,
        context=envelope,
        skill_context=None,
        peer_items=envelope["peer_context"],
        assigned_command={"task": "分析锁等待", "focus": "top sql"},
        to_json=json.dumps,
    )

    assert "Agent 专属分析上下文" in prompt
    assert "shared_context" in prompt
    assert "incident" not in prompt
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_agent_context_envelope.py -q`
Expected: FAIL because prompts still serialize the whole `context` payload.

**Step 3: Write minimal implementation**

Implement an explicit context envelope:
- `shared_context`: compact incident/session summary
- `focused_context`: per-agent narrow slice
- `tool_context`: tool and audit summary
- `peer_context`: peer conclusions
- `mailbox_context`: inbox command/feedback/evidence
- `work_log_context`: compact replay-oriented working set

Update prompts so experts see the envelope sections, not a raw whole-context dump.

**Step 4: Preserve audit compatibility**

Ensure `agent_tool_context_prepared` remains unchanged for replay/front-end consumers, and add only backward-compatible fields if needed.

**Step 5: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_agent_context_envelope.py backend/tests/test_agent_depth_contracts.py -q`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/runtime/langgraph_runtime.py backend/app/services/agent_tool_context_service.py backend/app/runtime/langgraph/prompt_builder.py backend/app/runtime/langgraph/prompts.py backend/app/runtime/langgraph/phase_executor.py backend/app/runtime/langgraph/nodes/agents.py backend/tests/runtime/test_agent_context_envelope.py backend/tests/test_agent_depth_contracts.py docs/agents/protocol-contracts.md docs/wiki/code_wiki_v2.md
git commit -m "feat: add explicit per-agent context envelope"
```

### Task 3: Make Experts Independent First, Collaborative Later

**Files:**
- Modify: `backend/app/runtime/langgraph/prompts.py`
- Modify: `backend/app/runtime/langgraph/prompt_builder.py`
- Modify: `backend/app/runtime/langgraph/phase_executor.py`
- Modify: `backend/app/runtime/langgraph/specs.py`
- Test: `backend/tests/test_routing_strategy_langgraph.py`
- Create: `backend/tests/runtime/test_expert_prompt_modes.py`
- Docs: `docs/agents/agent-catalog.md`

**Step 1: Write the failing test**

```python
def test_first_wave_analysis_prompt_allows_independent_evidence_collection():
    prompt = build_peer_driven_prompt(
        spec=AgentSpec(name="CodeAgent", role="代码专家", phase="analysis", system_prompt=""),
        loop_round=1,
        max_rounds=4,
        context={"shared_context": {"incident_summary": {"title": "orders 502"}}},
        skill_context=None,
        peer_items=[],
        assigned_command={"task": "定位代码闭包", "focus": "controller -> service -> dao"},
        to_json=json.dumps,
    )

    assert "禁止独立分析" not in prompt
    assert "先基于你的专属上下文独立取证" in prompt
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_expert_prompt_modes.py -q`
Expected: FAIL because current expert prompts force peer-dependent analysis too early.

**Step 3: Write minimal implementation**

Split expert prompt modes:
- first-wave analysis experts: independent evidence collection first, then optional peer comparison
- critique/rebuttal/judge/verification: explicitly peer-driven
- collaboration phase: compare/refute/merge prior evidence on purpose

Do not remove structured output requirements.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_expert_prompt_modes.py backend/tests/test_routing_strategy_langgraph.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/prompts.py backend/app/runtime/langgraph/prompt_builder.py backend/app/runtime/langgraph/phase_executor.py backend/app/runtime/langgraph/specs.py backend/tests/runtime/test_expert_prompt_modes.py backend/tests/test_routing_strategy_langgraph.py docs/agents/agent-catalog.md
git commit -m "feat: separate independent and peer-driven expert prompts"
```

### Task 4: Turn `analysis_depth_mode` Into a Real Runtime Policy

**Files:**
- Modify: `backend/app/runtime/langgraph/runtime_policy.py`
- Modify: `backend/app/runtime/langgraph/budgeting.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Modify: `backend/app/services/debate_service.py`
- Modify: `backend/app/api/debates.py`
- Modify: `backend/app/api/incidents.py`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/Incident/index.tsx`
- Modify: `frontend/src/pages/Settings/index.tsx`
- Test: `backend/tests/test_runtime_message_flow.py`
- Test: `backend/tests/test_p0_incident_debate_report.py`
- Create: `backend/tests/runtime/test_depth_policy_modes.py`
- Docs: `docs/agents/agent-catalog.md`
- Docs: `docs/agents/protocol-contracts.md`

**Step 1: Write the failing test**

```python
def test_deep_mode_expands_runtime_policy_beyond_round_count():
    policy = resolve_runtime_policy(
        {
            "execution_mode": "standard",
            "analysis_depth_mode": "deep",
        },
        debate_enable_critique=True,
        debate_enable_collaboration=True,
    )

    assert policy.max_discussion_steps > 8
    assert "ChangeAgent" in policy.parallel_analysis_agents
    assert policy.enable_critique is True
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_depth_policy_modes.py -q`
Expected: FAIL because current policy ignores `analysis_depth_mode`.

**Step 3: Write minimal implementation**

Define depth policy explicitly:
- `quick`: 1 round, reduced agent set, no critique/collaboration, lower token/time budgets
- `standard`: current balanced policy
- `deep`: more rounds, wider agent set, larger discussion budget, critique enabled, collaboration enabled when deployment allows, higher token/time budgets, stronger verification requirements

Make sure explicit `max_rounds` still overrides only round count, not the rest of the depth policy.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_depth_policy_modes.py backend/tests/test_runtime_message_flow.py backend/tests/test_p0_incident_debate_report.py -q`
Expected: PASS

**Step 5: Run frontend contract check**

Run: `npm run -s build`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/runtime/langgraph/runtime_policy.py backend/app/runtime/langgraph/budgeting.py backend/app/runtime/langgraph_runtime.py backend/app/services/debate_service.py backend/app/api/debates.py backend/app/api/incidents.py frontend/src/services/api.ts frontend/src/pages/Incident/index.tsx frontend/src/pages/Settings/index.tsx backend/tests/runtime/test_depth_policy_modes.py backend/tests/test_runtime_message_flow.py backend/tests/test_p0_incident_debate_report.py docs/agents/agent-catalog.md docs/agents/protocol-contracts.md
git commit -m "feat: promote analysis depth mode to full runtime policy"
```

### Task 5: Upgrade Coverage and Convergence Scoring for Complex Incidents

**Files:**
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Modify: `backend/app/models/debate.py`
- Modify: `backend/app/services/debate_service.py`
- Modify: `backend/app/services/report_generation_service.py`
- Modify: `backend/app/api/debates.py`
- Create: `backend/tests/runtime/test_coverage_and_convergence.py`
- Test: `backend/tests/test_p0_incident_debate_report.py`
- Docs: `docs/agents/protocol-contracts.md`

**Step 1: Write the failing test**

```python
def test_coverage_scoring_includes_weighted_domain_change_runbook_signals():
    coverage = orchestrator._count_key_evidence_coverage(
        [
            make_card("LogAgent", "analysis", confidence=0.8),
            make_card("CodeAgent", "analysis", confidence=0.8),
            make_card("DomainAgent", "analysis", confidence=0.8),
            make_card("ChangeAgent", "analysis", confidence=0.8),
        ]
    )

    assert "weighted_score" in coverage
    assert coverage["weighted_score"] > 0.5
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_coverage_and_convergence.py -q`
Expected: FAIL because current coverage is only `ok/degraded/missing` over a fixed four-agent set.

**Step 3: Write minimal implementation**

Add weighted coverage/convergence inputs:
- keep backward-compatible `ok/degraded/missing`
- add weighted dimensions for domain, change, runbook, and metrics corroboration
- expose richer `root_cause_candidates` metadata and convergence rationale in final payload/report generation

Do not break existing API consumers.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_coverage_and_convergence.py backend/tests/test_p0_incident_debate_report.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph_runtime.py backend/app/models/debate.py backend/app/services/debate_service.py backend/app/services/report_generation_service.py backend/app/api/debates.py backend/tests/runtime/test_coverage_and_convergence.py backend/tests/test_p0_incident_debate_report.py docs/agents/protocol-contracts.md
git commit -m "feat: enrich coverage and convergence scoring"
```

### Task 6: Close the Loop With Replay, Benchmarks, and Docs

**Files:**
- Modify: `docs/wiki/code_wiki_v2.md`
- Modify: `docs/agents/agent-catalog.md`
- Modify: `docs/agents/protocol-contracts.md`
- Modify: `docs/agents/tooling-and-audit.md`
- Create: `backend/tests/runtime/test_replay_context_contract.py`
- Modify: `backend/tests/test_agent_depth_contracts.py`
- Optional Verify: `scripts/smoke-e2e.mjs`

**Step 1: Write the failing test**

```python
def test_replay_payload_contains_context_envelope_and_depth_policy_fields():
    event = make_agent_tool_context_prepared_event()
    assert "focused_preview" in event
    assert "permission_decision" in event
    assert event["type"] == "agent_tool_context_prepared"
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_replay_context_contract.py backend/tests/test_agent_depth_contracts.py -q`
Expected: FAIL if replay/event fields drift during the refactor.

**Step 3: Update docs and compatibility notes**

Document:
- structured state authority
- agent context envelope
- independent-vs-peer-driven prompt phases
- deep-mode runtime policy semantics
- richer coverage/convergence contract

**Step 4: Run full targeted regression**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_structured_state_contract.py backend/tests/runtime/test_agent_context_envelope.py backend/tests/runtime/test_expert_prompt_modes.py backend/tests/runtime/test_depth_policy_modes.py backend/tests/runtime/test_coverage_and_convergence.py backend/tests/runtime/test_replay_context_contract.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py backend/tests/test_agent_depth_contracts.py backend/tests/test_p0_incident_debate_report.py -q`
Expected: PASS

**Step 5: Run smoke**

Run: `SMOKE_SCENARIO=order-502-db-lock node ./scripts/smoke-e2e.mjs`
Expected: `passed=1 failed=0`

**Step 6: Commit**

```bash
git add docs/wiki/code_wiki_v2.md docs/agents/agent-catalog.md docs/agents/protocol-contracts.md docs/agents/tooling-and-audit.md backend/tests/runtime/test_replay_context_contract.py backend/tests/test_agent_depth_contracts.py
git commit -m "docs: finalize langgraph context and depth remediation contracts"
```

## Notes

- Keep all protocol changes backward-compatible for frontend replay consumers.
- Preserve `debate_config_applied`, `agent_tool_context_prepared`, and `agent_tool_io` event shapes unless a consumer migration is implemented in the same batch.
- Prefer small PRs in task order; do not mix state normalization with depth-policy expansion in a single review.
- Use TDD for each task and request code review after each batch.
