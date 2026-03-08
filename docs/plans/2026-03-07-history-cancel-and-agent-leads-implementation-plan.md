# History Cancel And Agent Leads Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix cancel status drift and make all analysis agents consume responsibility-mapping-derived investigation leads.

**Architecture:** Keep the current supervisor-driven flow, but add a unified `investigation_leads` object after asset mapping. Enrich agent commands and tool contexts from that object instead of relying on one-off database-table injection.

**Tech Stack:** FastAPI, Pydantic, local file persistence, React, Ant Design, pytest.

---

### Task 1: Fix Cancel Status Consistency

**Files:**
- Modify: `backend/app/api/debates.py`
- Modify: `backend/app/api/ws_debates.py`
- Test: existing API flows via pytest / manual build

**Steps:**
1. Update REST cancel endpoint to sync incident status to `closed`.
2. Update WS cancel path to sync incident status to `closed`.
3. Verify history page now reflects cancelled status after refresh.

### Task 2: Add Investigation Leads Builder

**Files:**
- Modify: `backend/app/services/debate_service.py`

**Steps:**
1. Build a helper to derive `investigation_leads` from interface mapping, parsed data, runtime/dev/design assets.
2. Store leads into session context and returned assets.
3. Emit summary fields in mapping-related events where useful.

### Task 3: Enrich Agent Commands With Leads

**Files:**
- Modify: `backend/app/runtime/langgraph_runtime.py`

**Steps:**
1. Extend command extraction/enrichment to carry structured lead fields.
2. Add per-agent enrichment rules for Log/Domain/Code/Database/Metrics/Change/Runbook.
3. Include lead summary in `agent_command_issued` payload for auditability.

### Task 4: Enrich Tool Context With Leads

**Files:**
- Modify: `backend/app/services/agent_tool_context_service.py`

**Steps:**
1. Add lead extraction helpers for endpoints, classes, monitors, dependencies.
2. Feed these into each agent’s tool-context builder.
3. Ensure keyword extraction includes leads before falling back to generic tokens.

### Task 5: Update Docs And Tests

**Files:**
- Modify: `docs/agents/agent-catalog.md`
- Add/Modify: backend tests as needed

**Steps:**
1. Document the new lead-driven analysis responsibilities.
2. Add tests for cancel sync and governance of human review unaffected.
3. Run backend pytest, frontend typecheck, frontend build.
