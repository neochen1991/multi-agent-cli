# Governance And Benchmark SRE Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the `治理中心` and `评测中心` pages into SRE-facing operational surfaces that explain purpose first, show judgment first, and place advanced actions after context.

**Architecture:** Keep the current React, TypeScript, React Router, Ant Design, and existing API service contracts. The work is limited to frontend information architecture, page composition, shared presentation helpers, and CSS hierarchy updates.

**Tech Stack:** React, TypeScript, Ant Design, existing frontend API layer in `frontend/src/services/api.ts`, shared CSS in `frontend/src/styles/global.css`

---

### Task 1: Reframe Governance Center as an SRE control surface

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: manual browser verification on `/governance`

**Step 1: Write the failing expectation**

Current failure:

- the page title does not explain the page
- first screen does not answer current trust state
- actions and metadata have the same visual priority

**Step 2: Add a hero explanation section**

Implement a top hero card containing:

- new page title
- one-sentence page description
- intended user labels
- three plain-language questions the page answers

**Step 3: Add a critical status strip**

Create 4 to 6 compact summary cards for:

- active runtime profile
- latest quality trend conclusion
- pending remediation count
- timeout risk
- external sync state
- replay readiness

Each card must include short interpretation text, not only a number.

**Step 4: Add a recommended-next-action panel**

Implement derived summary logic in the page component that chooses one primary recommendation based on existing loaded data.

Examples:

- pending remediation exists
- timeout risk is high
- quality trend is degrading

**Step 5: Reorganize the long page into tabs or segmented sections**

Group current content into:

- `状态总览`
- `运行策略`
- `治理动作`
- `回放与审计`

Do not remove current capability blocks. Move them into the appropriate group.

**Step 6: Soften low-signal raw content**

Move raw JSON-like strings and long lists lower in the page or into collapsible containers.

**Step 7: Run validation**

Run:

```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run typecheck
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run build
```

Expected:

- both commands pass
- page still loads using the existing API layer

**Step 8: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add frontend/src/pages/GovernanceCenter/index.tsx frontend/src/styles/global.css
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: redesign governance center for sre workflows"
```

### Task 2: Reframe Benchmark Center as a quality judgment page

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/BenchmarkCenter/index.tsx`
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Test: manual browser verification on `/benchmark`

**Step 1: Write the failing expectation**

Current failure:

- the page leads with benchmark execution rather than quality interpretation
- metrics have no clear operational meaning
- history is a passive file list

**Step 2: Add a hero explanation section**

Implement a top hero card containing:

- new page title
- page purpose
- intended user
- three plain-language questions the page answers

**Step 3: Add a quality judgment strip**

Create summary cards for:

- top1 rate
- average overlap score
- timeout rate
- empty conclusion rate
- latest run freshness or sample size

Each card should include a short judgment hint such as:

- healthy
- watch
- risk

**Step 4: Move benchmark execution into a dedicated action card**

Keep the same controls, but place them in a clearly labeled action panel that explains when the user should run benchmark.

**Step 5: Reorganize content into tabs or segmented sections**

Group current content into:

- `结果总览`
- `样本明细`
- `历史趋势`

If no chart is added, history still needs stronger narrative labels and regression hints.

**Step 6: Add plain-language interpretation blocks**

Derive short explanations from existing metrics. Example:

- timeout rate high means response path may be unstable
- empty conclusion rate high means answer completeness is degraded

**Step 7: Run validation**

Run:

```bash
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run typecheck
cd /Users/neochen/multi-agent-cli_v2/frontend && npm run build
```

Expected:

- both commands pass
- benchmark page still functions with existing APIs

**Step 8: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add frontend/src/pages/BenchmarkCenter/index.tsx frontend/src/styles/global.css
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: redesign benchmark center for sre interpretation"
```

### Task 3: Create shared presentation primitives for advanced operational pages

**Files:**
- Modify: `/Users/neochen/multi-agent-cli_v2/frontend/src/styles/global.css`
- Create if needed: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/common/*`
- Test: visual verification on `/governance` and `/benchmark`

**Step 1: Identify repeated visual patterns**

Shared patterns expected:

- explanatory hero card
- summary metric strip
- recommendation card
- section subtitle text
- risk/health pill styles

**Step 2: Implement the minimum reusable layer**

Either:

- add page-local helper renderers

or

- extract very small shared components if duplication is substantial

Do not over-engineer a full design system.

**Step 3: Add shared CSS tokens and classes**

Implement styles for:

- hero layout
- metric strip
- health/risk states
- action cards
- secondary detail blocks

**Step 4: Validate responsive behavior**

Check that:

- the hero card stacks correctly on narrow screens
- metric cards wrap without becoming unreadable
- tab headers remain usable

**Step 5: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add frontend/src/styles/global.css frontend/src/components/common
git -C /Users/neochen/multi-agent-cli_v2 commit -m "feat: add shared advanced page presentation patterns"
```

### Task 4: Verify navigation wording and advanced-area consistency

**Files:**
- Modify if needed: `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Advanced/index.tsx`
- Modify if needed: `/Users/neochen/multi-agent-cli_v2/frontend/src/components/common/Sider/index.tsx`
- Test: manual click-through of advanced routes

**Step 1: Check wording consistency**

Verify that labels across:

- sider
- advanced landing page
- governance page
- benchmark page

match the new SRE-facing terminology.

**Step 2: Update wording if mismatched**

Examples:

- `治理中心` may remain as nav label, but page title should explain the page purpose
- `评测中心` may remain as nav label, but page hero should clarify quality interpretation

**Step 3: Manual verification**

Verify the user path:

- open `高级`
- choose `治理中心`
- understand page purpose from first screen
- choose `评测中心`
- understand quality status from first screen

**Step 4: Commit**

```bash
git -C /Users/neochen/multi-agent-cli_v2 add frontend/src/pages/Advanced/index.tsx frontend/src/components/common/Sider/index.tsx
git -C /Users/neochen/multi-agent-cli_v2 commit -m "chore: align advanced navigation wording with sre page goals"
```
