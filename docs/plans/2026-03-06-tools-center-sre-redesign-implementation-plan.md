# Tools Center SRE Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the tools center into a tool-health-first page that helps SREs judge trust while preserving connector control and trial capabilities for platform operators.

**Architecture:** Keep the current React, TypeScript, Ant Design, and existing tool registry, connector, trial, and audit APIs. Limit the work to page composition, derived health summaries, tab structure, and CSS hierarchy.

**Tech Stack:** React, TypeScript, Ant Design, `frontend/src/services/api.ts`, tool subcomponents under `frontend/src/components/tools`, shared CSS in `frontend/src/styles/global.css`

---

### Task 1: Reframe the page as a tool health workspace

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/ToolsCenter/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: manual browser verification on `/tools`

**Step 1: Write the failing expectation**

Current failure:

- the page starts from technical capability blocks, not tool trust
- connection actions and audit detail compete at the same visual level
- the page does not explain when an SRE should use it

**Step 2: Add a hero explanation card**

Implement:

- page title
- page purpose
- audience tags
- tool-trust question tags

**Step 3: Add a health summary strip**

Summarize:

- tool counts
- enabled tool counts
- connector counts
- unhealthy connector counts
- session audit status
- selected tool status

**Step 4: Add a recommended-next-action panel**

Derive one next step from current connector, tool, and audit states.

### Task 2: Reorganize content into SRE and operator task tabs

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/ToolsCenter/index.tsx`
- Reuse: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/tools/*`
- Test: manual browser verification on `/tools`

**Step 1: Define target tabs**

Use:

- `工具总览`
- `连接与试跑`
- `会话审计`
- `输出引用`

**Step 2: Re-map current blocks**

Map:

- registry list + detail panel -> `工具总览`
- connector actions + trial runner -> `连接与试跑`
- audit panel -> `会话审计`
- output ref preview -> `输出引用`

**Step 3: Keep operator controls intact**

Do not remove:

- connect
- disconnect
- list-tools
- call-tool
- trial run

### Task 3: Validate and align with advanced-area language

**Files:**
- Modify if needed: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Advanced/index.tsx`
- Test: manual click-through of `/advanced` -> `/tools`

**Step 1: Verify wording**

Make sure the tools page now reads as:

- tool trust
- connection control
- audit

not only as a developer utility page.

**Step 2: Run validation**

Run:

```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run typecheck
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run build
```

Expected:

- both commands pass
- existing tool page interactions still compile and render
