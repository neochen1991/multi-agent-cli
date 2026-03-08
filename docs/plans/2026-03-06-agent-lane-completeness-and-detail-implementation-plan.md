# Agent Lane Completeness And Detail Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure all participating agents appear in the sequence-lane graph, make the graph scrollable for larger agent sets, and show concrete interaction details when a step is clicked.

**Architecture:** Keep the current lane graph model and frontend data sources. Expand node derivation to use a multi-source union and add a detail panel derived from existing event records.

**Tech Stack:** React, TypeScript, existing Incident page state, CSS in `frontend/src/styles/global.css`

---

### Task 1: Expand lane node derivation

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`

**Step 1: Include round agents**

Build lane nodes from:

- debate events
- session rounds
- main agent

**Step 2: Keep edge logic unchanged**

Do not invent interactions for agents that only appear in rounds.

### Task 2: Add step detail support

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`

**Step 1: Derive matched events for selected step**

Use existing event records and interaction extraction helpers.

**Step 2: Render a detail panel**

Show concrete matched command / feedback / reply content.

### Task 3: Make lane graph scrollable

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/AgentNetworkGraph.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`

**Step 1: Add bounded scroll container**

Support larger lane counts without collapsing spacing.

### Task 4: Validate

**Step 1: Run validation**

Run:

```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run typecheck
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run build
```
