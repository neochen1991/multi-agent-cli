# Agent Network Sequence Visual Design

**Goal:** Replace the hard-to-read radial agent network with a beginner-friendly sequence-lane view in the incident analysis page.

**Problem:** The current graph only shows aggregated edges in a circular topology. It hides execution order, forces users to mentally reconstruct the flow, and makes repeated command/feedback patterns look like abstract graph theory instead of an investigation process.

**Chosen Approach:** Use a sequence-lane diagram.

- Each agent becomes one horizontal lane.
- `ProblemAnalysisAgent` stays at the top as the orchestrator lane.
- Interaction steps are rendered from left to right.
- Consecutive identical interactions are merged into one step with `xN`.
- Relation colors stay stable:
  - `command` = blue
  - `feedback` = green
  - `reply` = purple

**Why This Works Better**

- New users can read the chart as a process, not as a graph.
- The main question becomes obvious: who triggered whom, and who reported back.
- Repeated edges stop cluttering the screen because they are folded into grouped steps.

**Implementation Notes**

- Extend the front-end agent network model with ordered `steps`.
- Build steps from `debateEvents` in chronological order.
- Preserve aggregate node/edge counts for the summary bar.
- Replace the current SVG radial layout with a lane-based SVG timeline.

**Success Criteria**

- Users can identify the orchestrator and specialists at a glance.
- Users can follow the analysis from left to right without reading curved arrows.
- The graph remains readable on narrower screens via horizontal scrolling.
