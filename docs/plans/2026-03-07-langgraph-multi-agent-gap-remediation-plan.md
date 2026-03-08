# LangGraph Multi-Agent Gap Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split deployment graph topology from runtime strategy, restore missing protocol documentation, and land the minimum backend plumbing for explicit deployment profiles.

**Architecture:** Keep the current LangGraph runtime and add a lightweight deployment profile layer parallel to the existing runtime strategy layer. Thread the selected deployment profile through session creation, governance APIs, and orchestrator policy selection without changing frontend behavior in this iteration.

**Tech Stack:** FastAPI, Pydantic, LangGraph, Python dataclasses, pytest

---

### Task 1: Restore protocol documentation baseline

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/docs/agents/protocol-contracts.md`
- Modify: `/Users/neochen/multi-agent-cli_v2/AGENTS.md`

**Step 1: Write the missing protocol document**
Document the required event contracts and field expectations used by runtime, replay, skill audit, and tool audit.

**Step 2: Verify AGENTS navigation stays correct**
Ensure the repo-level navigation references a real file.

### Task 2: Add deployment profile center

**Files:**
- Create: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/deployment_center.py`
- Test: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_deployment_center.py`

**Step 1: Write the failing tests**
Cover default active profile behavior and automatic profile selection based on severity/execution mode.

**Step 2: Implement the deployment profile center**
Add profile registry, persisted active profile storage, and automatic selection.

**Step 3: Run targeted tests**
Run deployment-center tests.

### Task 3: Thread deployment profile through session creation

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- Test: `/Users/neochen/multi-agent-cli_v2/backend/tests/test_debate_service_deployment_profile.py`

**Step 1: Write the failing test**
Assert created session context contains both `runtime_strategy` and `deployment_profile`.

**Step 2: Implement minimal selection plumbing**
Use deployment center alongside runtime strategy center when creating a session.

**Step 3: Run targeted tests**
Run session-creation tests.

### Task 4: Expose deployment profiles via governance API

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/api/governance.py`

**Step 1: Add request model and endpoints**
Mirror runtime strategy endpoints for deployment profile list/get/set.

**Step 2: Keep payload shape symmetric**
Return active selection plus resolved profile details.

### Task 5: Apply deployment profile in runtime policy

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`

**Step 1: Read deployment profile from context**
Use it before runtime strategy in `_configure_runtime_policy`.

**Step 2: Keep behavior backward compatible**
If profile is missing or invalid, fall back to existing behavior.

### Task 6: Validate and document remaining gaps

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/docs/wiki/code_wiki_v2.md` (optional follow-up, not required in this iteration)

**Step 1: Run targeted backend tests**
Run pytest for the new tests and existing debate-service tests.

**Step 2: Summarize remaining work**
Call out P2 HITL and P4 benchmark work as follow-up items.
