# Agent Network Sequence Visual Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the radial agent network graph with a sequence-lane visualization that explains agent execution flow to beginners.

**Architecture:** Build ordered interaction steps in the incident page from chronological debate events, then render them with a lane-based SVG in the graph component. Keep summary counts and relation coloring so the rest of the UI stays consistent.

**Tech Stack:** React, TypeScript, Ant Design, SVG, existing incident debate event model

---

### Task 1: Extend Agent Network Data Model

**Files:**
- Modify: `frontend/src/components/incident/AgentNetworkGraph.tsx`
- Modify: `frontend/src/pages/Incident/index.tsx`

**Steps:**
1. Add a typed `AgentNetworkStep` model to the graph component.
2. Extend the graph props to accept ordered steps.
3. Build ordered steps from `debateEvents` in `Incident/index.tsx`.
4. Merge consecutive identical interactions into grouped steps with `count`.

### Task 2: Replace Radial Layout With Sequence Lanes

**Files:**
- Modify: `frontend/src/components/incident/AgentNetworkGraph.tsx`

**Steps:**
1. Remove circular positioning logic and curved edge rendering.
2. Render one lane per agent in stable order.
3. Render one interaction column per grouped step.
4. Draw straight connectors and centered relation cards between lanes.

### Task 3: Refresh Supporting Styles

**Files:**
- Modify: `frontend/src/styles/global.css`

**Steps:**
1. Replace radial graph styles with sequence-lane styles.
2. Add lane labels, lane lines, step cards, and relation chips.
3. Ensure small screens can horizontally scroll the sequence view cleanly.

### Task 4: Verify Build Output

**Files:**
- Modify: `frontend/src/components/incident/AgentNetworkGraph.tsx`
- Modify: `frontend/src/pages/Incident/index.tsx`
- Modify: `frontend/src/styles/global.css`

**Steps:**
1. Run `npm run typecheck`.
2. Run `npm run build`.
3. Confirm the sequence graph renders with grouped steps and no type regressions.
