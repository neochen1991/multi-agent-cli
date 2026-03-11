# Architecture Foundation Priority Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Strengthen the architecture foundation of the LangGraph runtime by making structured state authoritative, hardening judgment/review boundaries, and adding a minimal evidence graph without breaking existing result/report consumers.

**Architecture:** Keep the current `StateGraph` backbone and runtime contracts intact, but converge all writes onto structured state, carve out stable judgment/review boundary helpers, and extend final payloads with claim-graph fields as additive metadata. The implementation should preserve current smoke scenarios and frontend compatibility while reducing future drift.

**Tech Stack:** FastAPI, LangGraph, Python typed reducers, pytest, local smoke runner, markdown/json/html report generation.

---

### Task 1: Finish Structured State Authority Cleanup

**Files:**
- Modify: `backend/app/runtime/langgraph/state.py`
- Modify: `backend/app/runtime/langgraph/services/state_transition_service.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Test: `backend/tests/runtime/test_structured_state_contract.py`
- Test: `backend/tests/test_state_transition_service.py`

**Step 1: Write the failing test**

Add a regression that proves state writes do not depend on legacy flat merge order and that snapshot reconstruction preserves structured authority.

**Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/runtime/test_structured_state_contract.py backend/tests/test_state_transition_service.py -q
```

**Step 3: Write minimal implementation**

Implement:
- one shared helper for “node result -> structured state sync”
- removal of remaining ad hoc `flat + result -> snapshot` merge patterns on write paths
- short Chinese comments on all new synchronization helpers

**Step 4: Run targeted tests**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/runtime/test_structured_state_contract.py backend/tests/test_state_transition_service.py backend/tests/test_runtime_message_flow.py -q
```

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/state.py backend/app/runtime/langgraph/services/state_transition_service.py backend/app/runtime/langgraph_runtime.py backend/tests/runtime/test_structured_state_contract.py backend/tests/test_state_transition_service.py backend/tests/test_runtime_message_flow.py
git commit -m "refactor: make structured state authoritative"
```

### Task 2: Harden Judgment And Review Boundaries

**Files:**
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Modify: `backend/app/runtime/langgraph/execution.py`
- Modify: `backend/app/runtime/langgraph/builder.py`
- Create: `backend/app/runtime/langgraph/services/judgment_boundary.py`
- Create: `backend/app/runtime/langgraph/services/review_boundary.py`
- Test: `backend/tests/test_judge_payload_recovery.py`
- Test: `backend/tests/test_runtime_message_flow.py`

**Step 1: Write the failing test**

Add a regression that proves Judge input normalization and final payload generation can be called through a dedicated boundary helper, instead of reaching deep into runtime internals.

**Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_judge_payload_recovery.py backend/tests/test_runtime_message_flow.py -q
```

**Step 3: Write minimal implementation**

Implement:
- `judgment_boundary.py` for Judge input assembly / final payload normalization
- `review_boundary.py` for pending-review / resume state shaping
- Chinese comments on all new boundary helpers describing what must stay outside the main orchestrator

**Step 4: Run targeted tests**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_judge_payload_recovery.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py -q
```

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph_runtime.py backend/app/runtime/langgraph/execution.py backend/app/runtime/langgraph/builder.py backend/app/runtime/langgraph/services/judgment_boundary.py backend/app/runtime/langgraph/services/review_boundary.py backend/tests/test_judge_payload_recovery.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py
git commit -m "refactor: harden judgment and review boundaries"
```

### Task 3: Add Minimal Evidence Graph

**Files:**
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Modify: `backend/app/services/debate_service.py`
- Modify: `backend/app/services/report_generation_service.py`
- Test: `backend/tests/test_judge_payload_recovery.py`
- Test: `backend/tests/test_debate_service_effective_conclusion.py`
- Create: `backend/tests/test_evidence_graph_contract.py`

**Step 1: Write the failing test**

Add a regression that requires final payloads to expose additive claim-graph fields:
- `claims`
- `supports`
- `contradicts`
- `missing_checks`
- `eliminated_alternatives`

The test must verify old `evidence_chain` remains intact.

**Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_evidence_graph_contract.py backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py -q
```

**Step 3: Write minimal implementation**

Implement:
- claim graph synthesis from final judgment / alternatives / risk hints
- additive result/report compatibility only, no frontend-breaking field removals
- short Chinese comments on the new graph synthesis helpers

**Step 4: Run targeted tests**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_evidence_graph_contract.py backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_report_generation_service.py -q
```

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph_runtime.py backend/app/services/debate_service.py backend/app/services/report_generation_service.py backend/tests/test_evidence_graph_contract.py backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_report_generation_service.py
git commit -m "feat: add minimal evidence graph"
```

### Task 4: Sync Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/wiki/code_wiki_v2.md`
- Modify: `docs/agents/protocol-contracts.md`

**Step 1: Update docs**

Document:
- structured state as authoritative write path
- new judgment/review boundaries
- minimal evidence graph fields

**Step 2: Verify references**

Run:
```bash
python3 scripts/check-agents-md.py
```

**Step 3: Commit**

```bash
git add README.md docs/wiki/code_wiki_v2.md docs/agents/protocol-contracts.md
git commit -m "docs: update architecture foundation guidance"
```

### Task 5: Final Verification

**Files:**
- No code changes unless verification exposes regressions

**Step 1: Run backend regression suite**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/runtime/test_structured_state_contract.py backend/tests/test_state_transition_service.py backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_report_generation_service.py backend/tests/runtime/test_expert_subgraph.py backend/tests/test_langgraph_route_guardrail.py -q
```

**Step 2: Run smoke scenarios**

Run:
```bash
SMOKE_SCENARIO=order-404-route-miss node ./scripts/smoke-e2e.mjs
SMOKE_SCENARIO=payment-timeout-upstream node ./scripts/smoke-e2e.mjs
```

Expected:
- both `passed: 1/1`
- valid `report_id`
- final `confidence` preserved

**Step 3: Commit final fixes if needed**

```bash
git add .
git commit -m "test: verify architecture foundation upgrade"
```

