# Advanced Dashboard And Lite Charts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the advanced landing page into a navigation cockpit and add lightweight visual summaries to the governance, benchmark, investigation, and tools pages without adding a chart library.

**Architecture:** Keep the current React, TypeScript, Ant Design, and existing API contracts. Use CSS-based visual primitives, Ant Design layout components, and existing loaded page data to create lightweight charts and directional cues.

**Tech Stack:** React, TypeScript, Ant Design, existing page data from `frontend/src/pages/*`, shared CSS in `frontend/src/styles/global.css`

---

### Task 1: Rebuild the Advanced landing page as a navigation cockpit

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Advanced/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: manual browser verification on `/advanced`

**Step 1: Write the failing expectation**

Current failure:

- the page lists modules, but does not help the user choose the correct one
- the page has no scenario mapping
- the page has no advanced-area summary

**Step 2: Add task-first cards**

Replace or extend the current module grid so each card answers:

- when to use
- what it is for
- where to click

**Step 3: Add scenario guidance**

Implement a compact section mapping common questions to advanced pages.

**Step 4: Add platform status summary shell**

Add small summary cards that reinforce the mental model of the four advanced pages.

### Task 2: Add lightweight visuals to Governance and Benchmark pages

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/BenchmarkCenter/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: manual browser verification on `/governance` and `/benchmark`

**Step 1: Add CSS-based mini chart primitives**

Implement:

- ratio bars
- mini trend rows
- mini strip blocks

**Step 2: Add governance visual summary**

Use current data for:

- timeout concentration
- cost trend
- failure hotspots

**Step 3: Add benchmark visual summary**

Use current data for:

- baseline trend
- metric comparisons
- last run vs latest baseline

### Task 3: Add lightweight visuals to Investigation and Tools pages

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/InvestigationWorkbench/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/ToolsCenter/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: manual browser verification on `/workbench` and `/tools`

**Step 1: Add investigation visual summary**

Use current data for:

- replay density
- decision/tool/timeline ratios
- phase concentration if cheaply derivable

**Step 2: Add tools visual summary**

Use current data for:

- enabled vs disabled tool ratio
- healthy vs unhealthy connector ratio
- audit readiness

### Task 4: Validate advanced-area consistency

**Files:**
- Modify if needed: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Advanced/index.tsx`
- Modify if needed: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: click-through of `/advanced`, `/governance`, `/benchmark`, `/workbench`, `/tools`

**Step 1: Verify that the advanced area now reads as one family**

Check:

- consistent hero usage
- consistent summary strip rhythm
- consistent recommendation placement
- consistent mini-visual styling

**Step 2: Run validation**

Run:

```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run typecheck
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run build
```

Expected:

- both commands pass
- no new chart dependency is required
