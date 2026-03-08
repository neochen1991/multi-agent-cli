# LangGraph HITL Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a minimal graph-level human review pause/approve/reject/resume flow for `production_governed` sessions.

**Architecture:** Extend supervisor structured output and routing state with review metadata, then convert review requests into a persisted `WAITING` session checkpoint at the service layer. Approval resumes from saved debate payload before report generation, without replaying the full AI debate.

**Tech Stack:** FastAPI, LangGraph, Pydantic, pytest, React, TypeScript

---

### Task 1: Extend supervisor review contract

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/parsers.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/routing_helpers.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state.py`

**Step 1: Write failing tests**
Add backend tests asserting review fields survive parsing and route decision handling.

**Step 2: Implement structured review fields**
Pass `should_pause_for_review`, `review_reason`, `review_payload`, and `resume_from_step` through prompt -> parser -> route decision -> state.

**Step 3: Run tests**
Run targeted pytest for parser/state/service coverage.

### Task 2: Add waiting-review task/runtime state

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/task_registry.py`
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/session_store.py`
- Test: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_task_registry_review_waiting.py`

**Step 1: Add waiting-review state fields**
Persist review reason and resume step alongside task status.

**Step 2: Add helper methods**
Implement `mark_waiting_review(...)` and runtime-session waiting-review state persistence.

### Task 3: Add review pause/approve/reject/resume in DebateService

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- Test: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_debate_service_human_review.py`

**Step 1: Write failing tests**
Cover pause checkpoint, approval precondition, and rejection transition.

**Step 2: Implement pause checkpoint**
Persist pending debate payload/assets and transition to `WAITING` when review is required.

**Step 3: Implement decision methods**
Add approve/reject helpers and resume-from-review continuation path.

### Task 4: Wire WS controls

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/api/ws_debates.py`

**Step 1: Add `approve` and `reject` control messages**
Accept operator decision commands over WS.

**Step 2: Distinguish waiting-review from failure**
When review is required, broadcast waiting snapshot and avoid failed/error path.

### Task 5: Add minimal frontend controls

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`

**Step 1: Add review state display**
Show waiting-review reason and approval status.

**Step 2: Add control actions**
Expose `批准继续` and `驳回结束` next to existing session controls.

### Task 6: Validate end-to-end

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/agents/protocol-contracts.md`

**Step 1: Update protocol docs**
Document `human_review_requested`, `human_review_approved`, and `human_review_rejected`.

**Step 2: Run tests and typecheck**
Run backend pytest for new review tests and frontend `npm run typecheck`.
