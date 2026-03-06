# Frontend Information Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify the frontend into a task-oriented product structure centered on incidents, while moving governance and platform tooling into an advanced area.

**Architecture:** Keep the current React + Ant Design stack and existing backend APIs, but reorganize routes, navigation, and page composition. The main product flow becomes `Home -> Event Queue -> Incident Detail`, with advanced pages grouped under a separate navigation surface.

**Tech Stack:** React, TypeScript, React Router, Ant Design, existing frontend service layer in `frontend/src/services/api.ts`

---

### Task 1: Replace first-level navigation with the target IA

**Files:**
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/components/common/Sider/index.tsx)
- Modify: [App.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/App.tsx)
- Test: manual navigation smoke test in browser

**Step 1: Write the failing expectation list**

Document the target navigation labels in a scratch note before editing:

- `首页`
- `事件`
- `责任田`
- `设置`
- `高级`

Expected current failure:

- Existing nav still shows `历史记录` / `调查工作台` / `评测中心` / `治理中心` / `工具中心` as top-level items.

**Step 2: Implement minimal navigation restructuring**

Change the sider so that:

- `/incident` becomes `事件`
- `/assets` remains `责任田`
- `/settings` remains `设置`
- advanced routes map to one grouped `高级` entry or a dedicated advanced landing route

Keep route compatibility first. Do not delete routes yet.

**Step 3: Add route compatibility behavior**

Ensure legacy routes still load:

- `/history`
- `/workbench`
- `/benchmark`
- `/governance`
- `/tools`

But they should visually belong to the advanced area.

**Step 4: Manual verification**

Run:

```bash
npm run dev
```

Verify:

- Top-level navigation count is reduced.
- Route highlighting still works.
- Existing deep links remain usable.

**Step 5: Commit**

```bash
git add frontend/src/components/common/Sider/index.tsx frontend/src/App.tsx
git commit -m "feat: simplify top-level frontend navigation"
```

### Task 2: Create a single Event Queue mental model

**Files:**
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/History/index.tsx)
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx)
- Modify: [api.ts](/Users/neochen/multi-agent-cli_v2/frontend/src/services/api.ts)
- Test: manual incident list flow

**Step 1: Define the queue responsibilities**

Write the intended queue behaviors in code comments or task notes:

- list incidents
- filter incidents
- open incident detail
- resume running analysis
- start new analysis

Expected current failure:

- incident creation and history viewing are split across multiple unrelated pages.

**Step 2: Refactor the event list entry point**

Choose one page as the canonical queue page.

Recommended:

- use `frontend/src/pages/History/index.tsx` as the queue base
- rename displayed title and interactions to `事件`

**Step 3: Expose strong primary actions**

Add or keep obvious CTAs:

- `新建分析`
- `继续分析`
- `查看详情`

Remove low-signal controls from the default view.

**Step 4: Manual verification**

Verify:

- A user can reach the queue from navigation.
- A user can create or open an incident without reading other pages first.

**Step 5: Commit**

```bash
git add frontend/src/pages/History/index.tsx frontend/src/pages/Incident/index.tsx frontend/src/services/api.ts
git commit -m "feat: unify event queue entry experience"
```

### Task 3: Break Incident page into a stable detail layout

**Files:**
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx)
- Create: `frontend/src/pages/Incident/sections/*` if needed
- Test: manual incident detail flow

**Step 1: Extract the target tab structure**

Target tabs:

- `概览`
- `时间线`
- `证据`
- `责任田`
- `结论与行动`

Expected current failure:

- The page is a long, mixed workflow surface with too many simultaneous concepts.

**Step 2: Extract page sections into components**

Create small components for:

- incident header summary
- timeline panel
- evidence panel
- responsibility mapping panel
- result and action panel

Do not redesign backend data contracts in this task.

**Step 3: Re-map existing content into the new tabs**

Rules:

- execution state and top summary go to `概览`
- event stream and phase progression go to `时间线`
- evidence chain and source-derived findings go to `证据`
- domain / aggregate / team / owner go to `责任田`
- final judgment / verification / action items go to `结论与行动`

**Step 4: Keep advanced internals behind collapsible blocks**

Examples:

- raw tool audit payload
- full event JSON
- internal dedupe metadata

These should not dominate the default view.

**Step 5: Manual verification**

Verify:

- A first-time user can understand the incident state from the first screenful.
- Timeline reads as a narrative.
- Responsibility mapping is visible without hunting for it.

**Step 6: Commit**

```bash
git add frontend/src/pages/Incident/index.tsx frontend/src/pages/Incident
git commit -m "feat: restructure incident detail into focused tabs"
```

### Task 4: Move platform pages into an Advanced area

**Files:**
- Modify: [App.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/App.tsx)
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx)
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/BenchmarkCenter/index.tsx)
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/ToolsCenter/index.tsx)
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/InvestigationWorkbench/index.tsx)
- Test: manual advanced navigation flow

**Step 1: Create an advanced landing experience**

Add either:

- one advanced landing page with cards

or

- one advanced route with tabs / segmented navigation

Recommended labels:

- `回放与审计`
- `治理`
- `评测`
- `工具接入`

**Step 2: Re-label page titles**

Update each page title so it matches user goals rather than platform jargon where possible.

Examples:

- workbench -> `回放与审计`
- tools -> `工具接入`

**Step 3: Preserve direct route access**

Keep old routes working for compatibility, but point users toward the advanced grouping.

**Step 4: Manual verification**

Verify:

- Advanced pages no longer compete with primary user flow.
- Existing pages still render.

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/GovernanceCenter/index.tsx frontend/src/pages/BenchmarkCenter/index.tsx frontend/src/pages/ToolsCenter/index.tsx frontend/src/pages/InvestigationWorkbench/index.tsx
git commit -m "feat: group platform capabilities under advanced navigation"
```

### Task 5: Simplify the home page into a product landing page

**Files:**
- Modify: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Home/index.tsx)
- Test: manual home page usability check

**Step 1: Remove feature-catalog overload**

Reduce emphasis on agent taxonomy and platform-wide capability enumeration.

The page should answer:

- what this product does
- where the user should start
- what is happening now

**Step 2: Keep only high-signal cards**

Recommended homepage content:

- headline + one-sentence product definition
- `新建分析`
- `查看事件队列`
- compact health or volume summary
- recent incidents

**Step 3: Manual verification**

Verify:

- A new user can tell what to do next from the homepage in under 10 seconds.

**Step 4: Commit**

```bash
git add frontend/src/pages/Home/index.tsx
git commit -m "feat: simplify home page around primary user actions"
```

### Task 6: Update copy and labels to match business tasks

**Files:**
- Modify: relevant frontend pages under `frontend/src/pages`
- Test: manual terminology review

**Step 1: Replace internal platform language**

Audit and replace unclear labels such as:

- `调查工作台`
- `工具中心`
- `治理中心`

Where appropriate, use:

- `事件`
- `回放与审计`
- `平台治理`
- `工具接入`

**Step 2: Normalize CTA language**

Examples:

- `开始分析`
- `继续分析`
- `查看详情`
- `查看责任田`
- `查看回放`

**Step 3: Manual verification**

Read each primary page top to bottom and ensure the copy describes user tasks, not implementation internals.

**Step 4: Commit**

```bash
git add frontend/src/pages frontend/src/components/common/Sider/index.tsx
git commit -m "chore: normalize task-oriented frontend labels"
```

### Task 7: Regression verification

**Files:**
- Test only

**Step 1: Run frontend checks**

Run:

```bash
npm run dev
```

If lint exists, also run:

```bash
npm run lint
```

**Step 2: Manual end-to-end checks**

Verify these flows:

- home -> new analysis
- home -> event queue
- queue -> incident detail
- incident detail -> responsibility view
- incident detail -> result view
- advanced -> governance
- advanced -> replay
- advanced -> benchmark
- advanced -> tools

**Step 3: Confirm route compatibility**

Verify old direct URLs still open:

- `/history`
- `/workbench`
- `/benchmark`
- `/governance`
- `/tools`

**Step 4: Final commit**

```bash
git add frontend
git commit -m "feat: apply frontend information architecture redesign"
```

