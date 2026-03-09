# Figma Isolated Frontend V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a fully isolated Figma-driven frontend V2 for the home page and incident workbench while preserving the legacy frontend and backend contracts.

**Architecture:** Introduce a new `frontend/src/v2/` application slice with its own layout, pages, components, and stylesheet namespace. Keep existing API services and backend flows, but do not reuse legacy page/layout components; instead, wire new V2 pages directly to the same service layer and expose them via dedicated `/v2` routes plus a switch button on the legacy home page.

**Tech Stack:** React, React Router, Ant Design, Vite, existing frontend API services, Playwright MCP for visual verification.

---

### Task 1: Add isolated V2 routing shell

**Files:**
- Create: `frontend/src/v2/layout/V2Layout.tsx`
- Create: `frontend/src/v2/routes.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`

**Step 1: Write the failing integration expectation**

Expected route matrix:
- `/` -> legacy app
- `/v2` -> new home page shell
- `/v2/incident` -> new incident workbench shell

**Step 2: Implement minimal V2 routing shell**

- Add `V2Layout` with isolated `v2-*` class names.
- Add `routes.tsx` exporting `HomeV2` and `IncidentV2` route elements.
- Register `/v2` and `/v2/incident` in `frontend/src/App.tsx`.
- Import `frontend/src/v2/styles/v2.css` from `frontend/src/main.tsx`.

**Step 3: Verify route registration**

Run: `npm run build`
Expected: build passes, no route/type errors.

### Task 2: Build the V2 design system and layout primitives

**Files:**
- Create: `frontend/src/v2/styles/v2.css`
- Create: `frontend/src/v2/components/V2Header.tsx`
- Create: `frontend/src/v2/components/V2Sidebar.tsx`
- Create: `frontend/src/v2/components/V2Panel.tsx`
- Create: `frontend/src/v2/components/V2MetricCard.tsx`

**Step 1: Port first-version Figma tokens**

- Copy the first-version mock visual language from `frontend/public/figma-mockups/mockups.css`.
- Namespace all selectors with `v2-` to isolate from legacy styles.

**Step 2: Build reusable V2 primitives**

- `V2Header`: top bar, brand, status chip, time.
- `V2Sidebar`: navigation and side summary cards.
- `V2Panel`: standard content container.
- `V2MetricCard`: home dashboard metric tiles.

**Step 3: Verify style isolation**

Run: `npm run build`
Expected: no CSS import/type issues.

### Task 3: Implement Figma-style Home V2

**Files:**
- Create: `frontend/src/v2/pages/HomeV2.tsx`
- Modify: `frontend/src/pages/Home/index.tsx`

**Step 1: Build Home V2 from the first mock**

Match `frontend/public/figma-mockups/console-home.html` structure:
- top header area handled by `V2Layout`
- metric strip
- quick create form
- status side panels
- active incidents table
- completed analyses panel
- agent capability matrix

**Step 2: Wire to existing services**

Use existing `incidentApi` and `debateApi` for:
- dashboard stats
- recent incidents
- quick create + create session

**Step 3: Add legacy-to-v2 switch**

On the existing legacy home page add one button linking to `/v2`.
Do not remove legacy behavior.

**Step 4: Verify**

Run: `npm run build`
Expected: build passes.

### Task 4: Implement isolated Incident V2 workbench

**Files:**
- Create: `frontend/src/v2/pages/IncidentV2.tsx`
- Create: `frontend/src/v2/components/incident/V2ConclusionBand.tsx`
- Create: `frontend/src/v2/components/incident/V2IncidentInputPanel.tsx`
- Create: `frontend/src/v2/components/incident/V2SessionControlPanel.tsx`
- Create: `frontend/src/v2/components/incident/V2DebateStream.tsx`
- Create: `frontend/src/v2/components/incident/V2AuxiliaryViews.tsx`
- Create: `frontend/src/v2/components/incident/V2AssetColumn.tsx`
- Create: `frontend/src/v2/components/incident/V2ReportDrawer.tsx`

**Step 1: Match the first incident mock layout**

Mirror `frontend/public/figma-mockups/incident-workbench.html`:
- page header
- conclusion band
- left column: input + session control
- center column: debate process + auxiliary views
- right column: asset mapping + evidence + top-k
- report/result area separated from main workspace

**Step 2: Keep backend contract unchanged**

Use existing service layer and reuse data-fetching/event interpretation patterns from legacy incident page, but do not import legacy incident components.

**Step 3: Implement V2-only rendering adapters**

Create new mapping/adaptor helpers inside `IncidentV2.tsx` or nearby V2 helpers for:
- conclusion summary
- asset summary
- dialogue items
- event/timeline preview
- top-k candidate cards

**Step 4: Verify**

Run: `npm run build`
Expected: build passes.

### Task 5: Add navigation and switching entry points

**Files:**
- Modify: `frontend/src/components/common/Sider/index.tsx`
- Modify: `frontend/src/pages/Home/index.tsx`
- Modify: `frontend/src/v2/components/V2Sidebar.tsx`

**Step 1: Add clear entry points**

- Legacy home page button: `切换到新版工作台`
- Legacy sider optional link to `/v2`
- V2 sidebar links to `/v2` and `/v2/incident`
- V2 page header action to return to legacy `/`

**Step 2: Verify route switching**

Manual checks:
- legacy `/` remains usable
- `/v2` opens new UI
- `/v2/incident` opens new UI

### Task 6: Visual verification with Playwright

**Files:**
- No required source changes unless defects are found

**Step 1: Verify legacy + V2 coexistence**

Use Playwright MCP on:
- `http://127.0.0.1:5173/`
- `http://127.0.0.1:5173/v2`
- `http://127.0.0.1:5173/v2/incident`

**Step 2: Check layout at key widths**

Widths:
- `1440`
- `1280`
- `1100`

**Step 3: Fix only V2 defects**

If overlap/overflow issues are found, patch only `frontend/src/v2/styles/v2.css` or V2 components.

**Step 4: Final verification**

Run: `npm run build`
Expected: PASS

Run Playwright visual checks again.
Expected: No overlapping major panels on the tested widths.
