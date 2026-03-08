# LangGraph Multi-Agent Gap Remediation Design

**Context**

The current runtime already has strong audit, tool gating, skill injection, and replay capabilities. The main remaining gap versus stronger LangGraph multi-agent reference systems is structural clarity: runtime strategy and graph topology are still coupled, HITL is not yet modeled as a first-class graph state, and protocol documentation is incomplete.

**Problem Statement**

Current behavior mixes two different concerns:
- runtime strategy chooses prompt/context/round-pressure style
- runtime execution path still assumes one main graph shape

This makes it harder to reason about which features belong to:
- topology selection
- runtime tuning
- governance/HITL
- evaluation coverage

The repo also advertises `docs/agents/protocol-contracts.md` from [`AGENTS.md`](/Users/neochen/multi-agent-cli_v2/AGENTS.md), but that document is currently missing.

**Goals**

1. Restore documentation completeness for agent protocol contracts.
2. Split `deployment profile` from `runtime strategy`.
3. Make graph topology selection explicit at session creation time.
4. Keep implementation incremental so existing sessions and frontend flows continue to work.

**Non-Goals In This Iteration**

1. Full graph-level HITL interrupt/approve/resume.
2. Frontend UI for deployment profile management.
3. Full per-agent trajectory benchmark scoring.
4. Rewriting the whole runtime around subgraphs.

**Approach Options**

## Option A: Minimal layering on top of current runtime

Add a deployment profile registry and thread a `deployment_profile` through session context and runtime configuration. Keep the current `GraphBuilder` and make it topology-aware with small switches.

Pros:
- lowest risk
- preserves current runtime shape
- easy to test and ship incrementally

Cons:
- does not fully decouple graph construction from orchestrator policy yet

## Option B: Full deployments package with separate graph builders

Create a distinct deployment module per graph and let the runtime dispatch to different builders.

Pros:
- strongest separation
- closest to reference systems with multiple deployment graphs

Cons:
- larger refactor
- higher regression risk in current codebase

## Option C: Keep single runtime and only document deployment intent

Do not change code, only document the concept.

Pros:
- no code risk

Cons:
- does not solve architectural coupling
- not sufficient for long-term maintainability

**Recommendation**

Use Option A now. It creates a clean seam for future HITL and multi-graph work without destabilizing the running system.

**Design**

## 1. New deployment profile center

Add a new runtime service similar to `runtime_strategy_center`:
- `baseline`
- `skill_enabled`
- `investigation_full`
- `production_governed`

Each profile controls topology-oriented behavior such as:
- whether collaboration node is enabled
- whether critique/judge pressure is enabled
- whether verification plan is required
- which analysis agent set is available
- whether governance gating is expected later

## 2. Session context split

At session creation, store both:
- `runtime_strategy`
- `deployment_profile`

`runtime_strategy` remains responsible for token/cost/round tuning.
`deployment_profile` becomes responsible for graph behavior and agent set shape.

## 3. Orchestrator policy selection order

The runtime should read `deployment_profile` first for topology policy, then apply `runtime_strategy` for execution pressure. This creates a clean hierarchy:
- deployment decides graph shape
- strategy decides execution style

## 4. Governance API exposure

Add read/write API endpoints for deployment profiles mirroring runtime strategy endpoints. This keeps operational introspection symmetric.

## 5. Protocol documentation baseline

Create `docs/agents/protocol-contracts.md` to define event contracts for:
- `agent_command_issued`
- `agent_command_feedback`
- `agent_chat_message`
- `tool_audit`
- `skill_hit`
- `final_judgment`

This closes the broken repo navigation and gives future HITL/evaluation work a stable contract reference.

**Testing Strategy**

1. Unit test deployment profile selection defaults.
2. Unit test session creation includes both `runtime_strategy` and `deployment_profile`.
3. Run existing backend tests for debate session behavior.
4. Keep frontend untouched in this iteration.

**Follow-up Iterations**

1. Add graph-level HITL states and resume protocol.
2. Add frontend controls and visibility for deployment profile.
3. Extend benchmark scoring to routing/trajectory/skill correctness.
