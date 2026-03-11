# LangGraph Agent Best Practices Remaining Work Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the remaining LangGraph best-practice upgrades after the current workspace’s completed groundwork, focusing on true per-agent memory, deeper expert investigation, evidence-gap routing, stricter depth quality gates, and production-grade recovery/governance.

**Architecture:** Reuse the current `StateGraph` backbone, structured state snapshots, prompt envelope, and depth-budget modules already landed in the workspace. Build the remaining work on top of those foundations instead of redoing them: keep current replay/event contracts stable, add narrowly scoped state/model extensions, and only deepen the experts and routing logic where the present implementation still stops at single-shot analysis.

**Tech Stack:** FastAPI, LangGraph, LangChain/OpenAI, Python typed reducers, pytest, frontend replay/governance consumers, SQLite/Memory checkpointers.

---

## Current Workspace Assessment

The following items are already substantially present in the current workspace and should be treated as completed groundwork rather than reimplemented:

- Structured state scaffolding exists and is already consumed by key runtime paths:
  - `backend/app/runtime/langgraph/state.py`
  - `backend/app/runtime/langgraph/state_views.py`
  - `backend/tests/runtime/test_structured_state_contract.py`
- Explicit agent context envelope is present in prompt assembly and tests:
  - `backend/app/runtime/langgraph/prompt_builder.py`
  - `backend/app/runtime/langgraph/prompts.py`
  - `backend/tests/runtime/test_agent_context_envelope.py`
- Analysis experts already support `independent-first` prompt behavior:
  - `backend/app/runtime/langgraph/prompts.py`
  - `backend/tests/runtime/test_expert_prompt_modes.py`
- `analysis_depth_mode` already affects runtime policy and token/timeout budgets:
  - `backend/app/runtime/langgraph/runtime_policy.py`
  - `backend/app/runtime/langgraph/budgeting.py`
  - `backend/tests/runtime/test_depth_policy_modes.py`
  - `backend/tests/runtime/test_budgeting.py`
- Coverage and convergence scoring groundwork is present:
  - `backend/app/runtime/langgraph_runtime.py`
  - `backend/tests/runtime/test_coverage_and_convergence.py`
- Supervisor post-analysis/post-judge routing has already been tightened:
  - `backend/app/runtime/langgraph/routing_strategy.py`
  - `backend/tests/test_routing_strategy_langgraph.py`

The remaining work below should only target gaps that are still not implemented:

- no true `agent_local_state`
- no multi-step expert subgraph / follow-up tool loop
- routing is still mostly phase/count-driven rather than evidence-gap-driven
- deep mode still changes budgets more than final evidence-quality gates
- recovery/governance do not yet validate the richer runtime state

### Task 1: Finish Structured State Authority Cleanup

**Files:**
- Modify: `backend/app/runtime/langgraph/state.py`
- Modify: `backend/app/runtime/langgraph/services/state_transition_service.py`
- Modify: `backend/app/runtime/langgraph/nodes/supervisor.py`
- Modify: `backend/app/runtime/langgraph/nodes/agents.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Test: `backend/tests/runtime/test_structured_state_contract.py`
- Test: `backend/tests/test_runtime_message_flow.py`
- Test: `backend/tests/test_graph_builder.py`

**Step 1: Write the failing test**

```python
from app.runtime.langgraph.state import flatten_structured_state_view, structured_state_snapshot


def test_structured_state_writes_do_not_depend_on_legacy_flat_merge_order():
    state = {
        "phase_state": {"current_round": 2},
        "routing_state": {"next_step": "analysis_parallel"},
        "output_state": {"top_k_hypotheses": [{"agent_name": "LogAgent", "conclusion": "db lock"}]},
        "current_round": 1,
        "next_step": "speak:CodeAgent",
        "top_k_hypotheses": [{"agent_name": "CodeAgent", "conclusion": "stale"}],
    }

    flat = flatten_structured_state_view(state)
    snapshot = structured_state_snapshot(flat)

    assert flat["current_round"] == 2
    assert flat["next_step"] == "analysis_parallel"
    assert snapshot["output_state"]["top_k_hypotheses"][0]["conclusion"] == "db lock"
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_structured_state_contract.py -q`
Expected: FAIL if any node/runtime path still rebuilds mixed state via ad hoc flat merge order.

**Step 3: Write minimal implementation**

Implement:
- a single shared helper for node result -> structured state synchronization
- removal of remaining inline `merged_preview = {**dict(flat_state), **result}` style logic
- Chinese comments on all newly introduced synchronization helpers explaining why structured state must stay authoritative

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_structured_state_contract.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/state.py backend/app/runtime/langgraph/services/state_transition_service.py backend/app/runtime/langgraph/nodes/supervisor.py backend/app/runtime/langgraph/nodes/agents.py backend/app/runtime/langgraph_runtime.py backend/tests/runtime/test_structured_state_contract.py backend/tests/test_runtime_message_flow.py backend/tests/test_graph_builder.py
git commit -m "refactor: finish structured state authority cleanup"
```

### Task 2: Add True Per-Agent Local Memory

**Files:**
- Modify: `backend/app/runtime/langgraph/state.py`
- Modify: `backend/app/runtime/langgraph/nodes/agents.py`
- Modify: `backend/app/runtime/langgraph/phase_executor.py`
- Modify: `backend/app/runtime/langgraph/prompt_builder.py`
- Modify: `backend/app/runtime/langgraph/prompts.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Docs: `docs/agents/protocol-contracts.md`
- Create: `backend/tests/runtime/test_agent_local_state.py`

**Step 1: Write the failing test**

```python
from app.runtime.langgraph.state import structured_state_snapshot


def test_agent_local_state_persists_private_hypotheses_without_leaking_to_shared_context():
    snapshot = structured_state_snapshot(
        {
            "agent_local_state": {
                "CodeAgent": {
                    "private_hypotheses": ["transaction scope too wide"],
                    "verified_evidence_ids": ["evd_code_1"],
                    "missing_checks": ["confirm connection release path"],
                }
            }
        }
    )

    assert snapshot["agent_local_state"]["CodeAgent"]["private_hypotheses"] == ["transaction scope too wide"]
    assert "private_hypotheses" not in snapshot.get("context_summary", {})
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_agent_local_state.py -q`
Expected: FAIL because runtime state still lacks true per-agent private memory.

**Step 3: Write minimal implementation**

Implement:
- `agent_local_state: Dict[str, Dict[str, Any]]` in runtime state
- helper methods to read/write one agent’s local memory
- prompt envelope extension with `agent_local_context`
- Chinese comments on new local-memory reducer/helper code to explain privacy boundary and why it must not be broadcast by default

Do not expose `agent_local_context` to unrelated agents unless the supervisor explicitly promotes part of it into shared state.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_agent_local_state.py backend/tests/runtime/test_agent_context_envelope.py backend/tests/test_runtime_message_flow.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/state.py backend/app/runtime/langgraph/nodes/agents.py backend/app/runtime/langgraph/phase_executor.py backend/app/runtime/langgraph/prompt_builder.py backend/app/runtime/langgraph/prompts.py backend/app/runtime/langgraph_runtime.py docs/agents/protocol-contracts.md backend/tests/runtime/test_agent_local_state.py backend/tests/runtime/test_agent_context_envelope.py backend/tests/test_runtime_message_flow.py
git commit -m "feat: add private agent local memory"
```

### Task 3: Add Multi-Step Expert Investigation for Key Experts

**Files:**
- Create: `backend/app/runtime/langgraph/nodes/expert_subgraph.py`
- Modify: `backend/app/runtime/langgraph/builder.py`
- Modify: `backend/app/runtime/langgraph/execution.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Modify: `backend/app/services/agent_tool_context_service.py`
- Create: `backend/tests/runtime/test_expert_subgraph.py`
- Test: `backend/tests/test_agent_depth_contracts.py`

**Step 1: Write the failing test**

```python
def test_code_agent_subgraph_can_request_followup_tool_step_before_final_conclusion():
    result = {
        "plan": ["inspect controller", "inspect transaction boundary"],
        "needs_followup": True,
        "followup_tool": "git_repo_search",
    }

    assert result["needs_followup"] is True
    assert result["followup_tool"] == "git_repo_search"
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_expert_subgraph.py -q`
Expected: FAIL because expert execution is still single-shot and lacks a follow-up tool loop.

**Step 3: Write minimal implementation**

Implement a reusable expert investigation loop for `LogAgent`, `CodeAgent`, and `DatabaseAgent`:
- step A: output an investigation plan
- step B: request one targeted follow-up tool context
- step C: output final structured result

Guardrails:
- max 2 follow-up steps
- preserve current tool audit events
- fall back to current single-shot mode for all other agents

All new core control logic must include short Chinese comments explaining the phase transition and stop conditions.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_expert_subgraph.py backend/tests/test_agent_depth_contracts.py backend/tests/test_runtime_message_flow.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/nodes/expert_subgraph.py backend/app/runtime/langgraph/builder.py backend/app/runtime/langgraph/execution.py backend/app/runtime/langgraph_runtime.py backend/app/services/agent_tool_context_service.py backend/tests/runtime/test_expert_subgraph.py backend/tests/test_agent_depth_contracts.py backend/tests/test_runtime_message_flow.py
git commit -m "feat: add iterative investigation subgraphs for key experts"
```

### Task 4: Make Routing Evidence-Gap Driven and Reduce Broadcast Noise

**Files:**
- Modify: `backend/app/runtime/langgraph/routing_strategy.py`
- Modify: `backend/app/runtime/langgraph/routing/rule_engine.py`
- Modify: `backend/app/runtime/langgraph/nodes/supervisor.py`
- Modify: `backend/app/runtime/langgraph/phase_executor.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Create: `backend/tests/runtime/test_evidence_gap_routing.py`
- Test: `backend/tests/test_routing_strategy_langgraph.py`

**Step 1: Write the failing test**

```python
def test_supervisor_prefers_agent_that_closes_current_evidence_gap():
    evidence_coverage = {"ok": 2, "degraded": 0, "missing": 2}
    open_questions = ["what SQL is blocking?", "is latency caused by DB or app retry storm?"]
    next_step = "speak:DatabaseAgent"

    assert evidence_coverage["missing"] == 2
    assert "DatabaseAgent" in next_step
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_evidence_gap_routing.py backend/tests/test_routing_strategy_langgraph.py -q`
Expected: FAIL because current routing still leans on phase/count progress more than explicit evidence-gap scoring.

**Step 3: Write minimal implementation**

Implement:
- agent-specialty gap scoring from `open_questions`, `round_gap_summary`, and `top_k_hypotheses`
- supervisor command generation that targets the highest-value unresolved gap
- selective evidence delivery instead of current broad peer broadcast

Rule:
- always send to `ProblemAnalysisAgent`
- only send to specialists whose domain matches the unresolved gap

Add Chinese comments on new scoring/routing helpers because this logic will be hard to reconstruct later from tests alone.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_evidence_gap_routing.py backend/tests/test_routing_strategy_langgraph.py backend/tests/test_runtime_message_flow.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/routing_strategy.py backend/app/runtime/langgraph/routing/rule_engine.py backend/app/runtime/langgraph/nodes/supervisor.py backend/app/runtime/langgraph/phase_executor.py backend/app/runtime/langgraph_runtime.py backend/tests/runtime/test_evidence_gap_routing.py backend/tests/test_routing_strategy_langgraph.py backend/tests/test_runtime_message_flow.py
git commit -m "feat: route by evidence gaps and narrow evidence fan-out"
```

### Task 5: Turn Depth Mode into an Evidence-Quality Gate

**Files:**
- Modify: `backend/app/runtime/langgraph/runtime_policy.py`
- Modify: `backend/app/runtime/langgraph/budgeting.py`
- Modify: `backend/app/runtime/langgraph/specs.py`
- Modify: `backend/app/runtime/langgraph/prompts.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Docs: `docs/agents/agent-catalog.md`
- Docs: `docs/agents/protocol-contracts.md`
- Create: `backend/tests/runtime/test_depth_quality_gates.py`

**Step 1: Write the failing test**

```python
def test_deep_mode_requires_cross_source_and_alternative_elimination():
    verdict = {
        "analysis_depth_mode": "deep",
        "evidence_chain": [{"type": "log"}, {"type": "code"}],
        "alternatives": [{"candidate": "cache issue", "why_not_selected": "timing mismatch"}],
        "verification_plan": [{"objective": "replay lock wait path"}],
    }

    assert verdict["analysis_depth_mode"] == "deep"
    assert len(verdict["evidence_chain"]) >= 2
    assert verdict["alternatives"][0]["why_not_selected"]
    assert verdict["verification_plan"]
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_depth_quality_gates.py -q`
Expected: FAIL because deep mode currently changes budget more than final output quality thresholds.

**Step 3: Write minimal implementation**

Implement depth quality rules:
- `quick`: allow fast stop with one strong source
- `standard`: require at least two source classes or one explicit missing-evidence notice
- `deep`: require cross-source evidence, counter-evidence, alternative-cause rejection, and verification plan

Enforce these gates in round evaluation and final verdict normalization.

Add Chinese comments on all newly introduced gate conditions so future reviewers understand why a session did or did not converge.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_depth_quality_gates.py backend/tests/runtime/test_depth_policy_modes.py backend/tests/runtime/test_coverage_and_convergence.py backend/tests/test_p0_incident_debate_report.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/runtime_policy.py backend/app/runtime/langgraph/budgeting.py backend/app/runtime/langgraph/specs.py backend/app/runtime/langgraph/prompts.py backend/app/runtime/langgraph_runtime.py docs/agents/agent-catalog.md docs/agents/protocol-contracts.md backend/tests/runtime/test_depth_quality_gates.py backend/tests/runtime/test_depth_policy_modes.py backend/tests/runtime/test_coverage_and_convergence.py backend/tests/test_p0_incident_debate_report.py
git commit -m "feat: enforce depth-specific evidence quality gates"
```

### Task 6: Harden Checkpoint Recovery for Richer Runtime State

**Files:**
- Modify: `backend/app/runtime/langgraph/checkpointer.py`
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Modify: `backend/app/runtime/session_store.py`
- Create: `backend/tests/runtime/test_checkpoint_recovery.py`
- Docs: `docs/agents/checkpoint-resume.md`

**Step 1: Write the failing test**

```python
def test_runtime_resume_restores_agent_local_state_and_mailbox():
    restored = {
        "routing_state": {"next_step": "speak:JudgeAgent"},
        "agent_local_state": {"CodeAgent": {"private_hypotheses": ["db lock"]}},
        "agent_mailbox": {"JudgeAgent": [{"sender": "CodeAgent", "message_type": "evidence"}]},
    }

    assert restored["routing_state"]["next_step"] == "speak:JudgeAgent"
    assert restored["agent_local_state"]["CodeAgent"]["private_hypotheses"] == ["db lock"]
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_checkpoint_recovery.py -q`
Expected: FAIL because current recovery coverage does not prove richer runtime state survives resume.

**Step 3: Write minimal implementation**

Implement:
- resume validation for `agent_local_state`, `agent_mailbox`, and `routing_state`
- schema compatibility checks for persisted checkpoints
- Chinese comments in recovery helpers to explain which fields are mandatory for replay-safe resume

Do not change existing event payload shapes.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_checkpoint_recovery.py backend/tests/test_runtime_message_flow.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/checkpointer.py backend/app/runtime/langgraph_runtime.py backend/app/runtime/session_store.py backend/tests/runtime/test_checkpoint_recovery.py docs/agents/checkpoint-resume.md
git commit -m "feat: harden checkpoint recovery for richer runtime state"
```

### Task 7: Add Governance Metrics for Depth Quality and Routing Precision

**Files:**
- Modify: `backend/app/services/governance_ops_service.py`
- Modify: `backend/app/runtime/langgraph/work_log_manager.py`
- Create: `backend/tests/runtime/test_depth_governance_metrics.py`
- Docs: `docs/agents/reliability-governance.md`

**Step 1: Write the failing test**

```python
def test_governance_report_flags_shallow_deep_mode_verdict():
    report = {
        "analysis_depth_mode": "deep",
        "cross_source_count": 1,
        "alternative_rejections": 0,
        "targeted_delivery_ratio": 0.2,
        "status": "degraded",
    }

    assert report["status"] == "degraded"
```

**Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_depth_governance_metrics.py -q`
Expected: FAIL because governance reporting does not yet score depth-quality and routing-precision expectations explicitly.

**Step 3: Write minimal implementation**

Implement governance metrics for:
- cross-source evidence count
- counter-evidence presence
- alternative root-cause elimination
- targeted-vs-broadcast evidence ratio
- resumed-session fidelity

Add short Chinese comments on any new scoring fields whose semantics are not obvious from the field name alone.

**Step 4: Run targeted tests**

Run: `backend/.venv/bin/pytest backend/tests/runtime/test_depth_governance_metrics.py backend/tests/test_governance_human_review.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/governance_ops_service.py backend/app/runtime/langgraph/work_log_manager.py backend/tests/runtime/test_depth_governance_metrics.py docs/agents/reliability-governance.md
git commit -m "feat: add governance metrics for depth quality and routing precision"
```
