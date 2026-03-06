# Investigation Workbench SRE Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the investigation workbench into a replay-first SRE page that explains conclusions and next actions before exposing raw audit detail.

**Architecture:** Keep the current React, TypeScript, Ant Design, and existing replay/lineage/report APIs. Limit the work to page composition, derived summary logic, tab structure, and CSS hierarchy.

**Tech Stack:** React, TypeScript, Ant Design, `frontend/src/services/api.ts`, shared CSS in `frontend/src/styles/global.css`

---

### Task 1: Reframe the page as a replay workspace

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/InvestigationWorkbench/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: manual browser verification on `/workbench`

**Step 1: Write the failing expectation**

Current failure:

- the page reads like a debugging console
- first screen does not explain final conclusion or next step
- raw audit and replay content have equal visual weight

**Step 2: Add a hero explanation card**

Implement:

- page title
- one-sentence page purpose
- audience tags
- question tags

**Step 3: Add a summary strip**

Create summary cards for:

- session status
- root cause
- confidence
- decision count
- tool calls
- report versions

**Step 4: Add a recommended-next-action panel**

Derive one recommendation from existing loaded data.

**Step 5: Move load controls into a dedicated control card**

Keep all current controls, but separate them from the hero and the replay content.

**Step 6: Run validation**

Run:

```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run typecheck
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run build
```

Expected:

- both commands pass
- current replay and report APIs continue to work unchanged

### Task 2: Reorganize content into replay-task tabs

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/InvestigationWorkbench/index.tsx`
- Test: manual browser verification on `/workbench`

**Step 1: Define target tabs**

Use:

- `复盘总览`
- `关键决策`
- `证据与工具`
- `报告对比`
- `原始审计`

**Step 2: Re-map existing blocks**

Map content as follows:

- conclusion, evidence chain, replay steps -> `复盘总览`
- key decisions, timeline -> `关键决策`
- evidence refs, tool audit -> `证据与工具`
- report diff, version table -> `报告对比`
- raw lineage list -> `原始审计`

**Step 3: Keep advanced details but soften them**

Use subtler cards or lower-priority presentation for raw audit content.

**Step 4: Validate default reading path**

Check that a user can:

- load a session
- understand conclusion from first screen
- follow the recommended next area

### Task 3: Align visual language with governance and benchmark pages

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: visual verification across `/governance`, `/benchmark`, `/workbench`

**Step 1: Reuse current operational page primitives**

Use the existing:

- hero card styles
- summary card styles
- recommendation card styles

**Step 2: Add minimum extra styles for replay page**

Only add page-specific styles if truly needed for:

- dual-column content
- longer replay lists
- raw audit labeling

**Step 3: Validate consistency**

Make sure the three advanced pages now feel like one product family.
