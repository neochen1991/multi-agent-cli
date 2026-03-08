# LangGraph HITL Review Design

**Context**

The runtime already supports resume/reconnect and governance-side remediation approval, but human review is not part of the LangGraph execution state itself. Sessions can resume after disconnect, yet they cannot pause in a first-class way for operator approval inside the RCA flow.

**Goal**

Add a minimal graph-level HITL review mechanism for the `production_governed` deployment profile.

**Scope**

This iteration only supports one review checkpoint:
- after AI debate has produced a usable judgment
- before report generation and final completion

This keeps resume semantics simple and avoids arbitrary node interruption.

**Approach Options**

## Option A: Minimal review checkpoint after debate, before report generation

- Supervisor can request review via structured fields.
- LangGraph state carries review metadata.
- Debate service converts that into `WAITING` session state.
- Approval resumes from saved debate payload, not by replaying the whole graph.

Pros:
- minimal risk
- true graph-aware review
- deterministic resume point

Cons:
- only one review checkpoint

## Option B: General interrupt/resume anywhere in graph

Pros:
- most flexible

Cons:
- much larger refactor
- significantly higher regression risk

## Option C: Keep review outside graph and only sync governance actions

Pros:
- easiest to implement

Cons:
- still not real graph-level HITL

**Recommendation**

Use Option A.

**Design**

## 1. Supervisor review fields

Extend `ProblemAnalysisAgent` structured supervisor output with:
- `should_pause_for_review`
- `review_reason`
- `review_payload`

These fields are only honored when deployment profile is `production_governed`.

## 2. LangGraph state additions

Add lightweight routing-state fields:
- `awaiting_human_review`
- `human_review_reason`
- `human_review_payload`
- `resume_from_step`

Supervisor node writes these fields into state when review is requested.

## 3. Runtime final payload contract

When finalize sees `awaiting_human_review=true`, it should still produce a structured payload, but mark it as review-paused instead of completed. The final judgment remains available, so downstream service logic can store a resumable checkpoint.

## 4. Debate service waiting-review checkpoint

After `_execute_ai_debate(...)` returns, `DebateService` checks for review-pause metadata.
If present:
- session status becomes `WAITING`
- current phase stays `JUDGMENT`
- pending debate payload and assets are stored in session context
- a `HumanReviewRequired` exception is raised to the WS driver

This lets WebSocket/task registry differentiate `waiting_review` from `failed`.

## 5. Review decision flow

New service methods:
- `approve_human_review(session_id, approver, comment)`
- `reject_human_review(session_id, approver, reason)`

Approve:
- records audit event
- stores approval metadata
- session remains resumable

Reject:
- records audit event
- transitions session to `FAILED`
- stores human rejection reason

Resume:
- only allowed after approval
- continues from stored pending debate payload directly into report generation + result persistence

## 6. Task/runtime state

Task registry gets a dedicated runtime status:
- `waiting_review`

Runtime session store also marks session as `waiting_review` for checkpoint visibility.

## 7. Frontend minimum support

In `Incident` page:
- recognize `waiting_review`
- display review reason in process controls
- add `批准继续` and `驳回结束`
- keep `恢复分析` only for already approved waiting sessions

No full approval workbench is added in this iteration.

**Testing**

1. Unit test deployment-governed review pause path.
2. Unit test approve flow and resume precondition.
3. Unit test reject flow transitions session to failed.
4. Typecheck frontend after adding minimal controls.

**Follow-up**

1. Add governance-center review queue.
2. Support multiple review checkpoints.
3. Extend benchmark to score review-trigger correctness.
