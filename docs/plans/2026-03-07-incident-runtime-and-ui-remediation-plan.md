# Incident Runtime And UI Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stabilize runtime analysis, make degraded evidence explicit, slim incident realtime rendering, and improve judgment quality when evidence coverage is poor.

**Architecture:** Split the fix into backend scheduling/gating, backend degraded-evidence semantics, frontend event-stream slimming, and prompt reduction. Keep the existing multi-agent architecture and APIs; change execution policy and presentation semantics.

**Tech Stack:** Python, FastAPI backend runtime, LangGraph orchestration, React, TypeScript, Ant Design.

---

### Task 1: Batch analysis execution and expose degraded evidence state

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/phase_executor.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Test: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`

**Step 1: Write failing tests**
- Add a test that simulates analysis fan-out and asserts execution happens in batches instead of one flat gather.
- Add a test that timeout fallback turns carry degraded fields.

**Step 2: Run targeted tests to confirm failure**
Run: `pytest backend/tests/test_runtime_message_flow.py -q`

**Step 3: Implement batching and degraded markers**
- Introduce evidence-agent batches in `PhaseExecutor.run_parallel_analysis_phase`.
- Mark fallback outputs and fan-in payloads with degraded metadata.

**Step 4: Run tests and fix edge cases**
Run: `pytest backend/tests/test_runtime_message_flow.py -q`

### Task 2: Gate judge behavior on evidence coverage and tool-disabled states

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/routing_helpers.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- Test: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_judge_payload_recovery.py`
- Test: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_p0_incident_debate_report.py`

**Step 1: Write failing tests**
- Assert that degraded key evidence agents prevent normal judge-ready state.
- Assert that placeholder/degraded outcomes are not promoted as effective conclusions.

**Step 2: Run targeted tests to confirm failure**
Run: `pytest backend/tests/test_judge_payload_recovery.py backend/tests/test_p0_incident_debate_report.py -q`

**Step 3: Implement evidence coverage gating**
- Add helpers to classify degraded evidence and tool-disabled evidence.
- Update judge readiness and final-payload promotion rules.

**Step 4: Re-run tests**
Run: `pytest backend/tests/test_judge_payload_recovery.py backend/tests/test_p0_incident_debate_report.py -q`

### Task 3: Slim frontend realtime rendering path

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`

**Step 1: Implement buffered event ingestion**
- Batch incoming realtime events before updating React state.
- Keep a tighter main-process event subset for primary tabs.

**Step 2: Reduce heavy recomputation**
- Build dialogue/network/timeline from aggregated events instead of the full raw set.
- Cap timeline rendering and move raw noise to audit-oriented views only.

**Step 3: Verify frontend type safety**
Run: `cd frontend && npm run typecheck`

**Step 4: Verify build**
Run: `cd frontend && npm run build`

### Task 4: Prompt slimming for commander and evidence agents

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompt_builder.py`
- Test: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_runtime_message_flow.py`

**Step 1: Trim duplicated prompt boilerplate**
- Reduce repeated instruction blocks.
- Shrink dialogue/history slices.

**Step 2: Keep output contracts intact**
- Preserve structured output requirements while reducing context volume.

**Step 3: Verify targeted tests**
Run: `pytest backend/tests/test_runtime_message_flow.py -q`

### Task 5: Final validation on runtime and frontend

**Files:**
- Modify if needed: touched files above

**Step 1: Run backend regression subset**
Run: `pytest backend/tests/test_runtime_message_flow.py backend/tests/test_judge_payload_recovery.py backend/tests/test_p0_incident_debate_report.py -q`

**Step 2: Run frontend checks**
Run: `cd frontend && npm run typecheck && npm run build`

**Step 3: Summarize the incident-specific fix outcomes**
- Explain which issue was runtime, which was frontend, and which was prompt-related.
