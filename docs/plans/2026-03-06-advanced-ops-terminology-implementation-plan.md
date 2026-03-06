# Advanced Ops Terminology Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace conversational wording in the advanced area with concise operations-console terminology.

**Architecture:** Keep all current page structures and behaviors. Limit the work to visible titles, section labels, summary labels, and surrounding helper copy.

**Tech Stack:** React, TypeScript, existing frontend pages under `frontend/src/pages`

---

### Task 1: Rename advanced landing page wording

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Advanced/index.tsx`

**Step 1: Replace high-level labels**

Update:

- page title
- navigation section labels
- scenario section labels
- summary section labels

**Step 2: Tighten helper copy**

Keep explanations, but make them sound operational rather than conversational.

### Task 2: Rename module page titles and summary labels

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/BenchmarkCenter/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/InvestigationWorkbench/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/ToolsCenter/index.tsx`

**Step 1: Replace page titles**

Use the approved operations-style names.

**Step 2: Replace repeated summary labels**

Update repeated titles such as:

- `推荐下一步` -> `处置建议`

### Task 3: Validate build

**Files:**
- No additional files required

**Step 1: Run validation**

Run:

```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run typecheck
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run build
```
