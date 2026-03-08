# Agent Lane Completeness And Detail Design

## Goal

Fix the sequence-lane Agent graph so that:

- all participating agents appear in lanes
- the lane area remains usable when agent count grows
- clicking a step shows concrete command / feedback / reply details

## Problem

The current lane graph builds nodes mainly from edge-producing events in `debateEvents`.

This misses agents that:

- exist in `sessionDetail.rounds`
- appear in the analysis flow but do not produce an extracted edge

As a result, some agents participate in the session but do not appear as lanes.

## Design

### 1. Node source becomes a multi-source union

Lane nodes should come from:

- extracted network interactions from `debateEvents`
- agent names from `sessionDetail.rounds`
- `ProblemAnalysisAgent`

If an agent has no explicit edge, keep the lane but do not fabricate an interaction.

### 2. Lane area becomes scrollable

If the lane count grows, the graph should support:

- vertical scrolling for the lane list
- horizontal scrolling for the step sequence

The graph remains one scrollable workspace instead of collapsing spacing.

### 3. Step click shows concrete interaction detail

Clicking a step should:

- keep the existing process filtering behavior
- open a detail block showing the actual events related to that step

The detail block should show:

- relation type
- source
- target
- matched event rows
- concrete text / summary

## Scope

Frontend only:

- `frontend/src/pages/Incident/index.tsx`
- `frontend/src/components/incident/AgentNetworkGraph.tsx`
- `frontend/src/components/incident/DebateProcessPanel.tsx`
- `frontend/src/styles/global.css`
