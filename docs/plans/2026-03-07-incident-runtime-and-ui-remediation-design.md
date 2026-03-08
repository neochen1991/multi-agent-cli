# Incident Runtime And UI Remediation Design

## Background

`inc_b3c54885` exposed a coupled failure across runtime scheduling, tool execution semantics, frontend event rendering, and prompt size:

- analysis fan-out sent multiple evidence agents into the LLM queue at once;
- key evidence agents timed out in queue and produced fallback feedback instead of real analysis;
- the UI rendered low-level LLM stream/http events inside the main analysis experience, causing heavy recomputation and visible lag;
- the judge still produced a normal-looking decision path even when most evidence agents had degraded.

The result was slow analysis, noisy logs, misleading “agent replied” semantics, and low-quality conclusions.

## Goals

1. Prevent key evidence agents from degrading en masse due to queue timeout.
2. Distinguish real evidence collection from degraded fallback execution.
3. Keep the incident detail page responsive during realtime runs.
4. Ensure final judgment is blocked or downgraded when key evidence is missing.
5. Reduce prompt weight where it materially affects latency.

## Non-Goals

- No redesign of the overall multi-agent architecture.
- No new backend APIs for this round.
- No full prompt rewrite or model/provider switch.

## Design

### 1. Staggered analysis execution

The analysis phase will stop launching all evidence agents in one `asyncio.gather` wave.

Instead, evidence agents will run in batches:

- batch 1: `DatabaseAgent`, `MetricsAgent`
- batch 2: `LogAgent`, `CodeAgent`
- batch 3: remaining analysis agents

This keeps the runtime within the current semaphore and queue budget, while still preserving partial parallelism.

Each batch will emit explicit events so the frontend can show stage progression without replaying every low-level LLM event.

### 2. Degraded evidence semantics

Fallback turns created from timeout/rate-limit/tool-disabled conditions will be marked as degraded evidence, not as normal completed analysis.

New output-level flags and feedback fields:

- `degraded: true`
- `degrade_reason`
- `evidence_status: degraded | missing | collected`
- `tool_status: disabled | skipped | ok`

`agent_command_feedback` will carry these fields so the UI and downstream judge logic can distinguish:

- real expert evidence
n- tool-disabled fallback
- queue-timeout fallback

### 3. Judge gating on evidence coverage

Judgment must not proceed as if analysis succeeded when critical evidence agents degraded.

Runtime will compute evidence coverage for key agents:

- `LogAgent`
- `CodeAgent`
- `DatabaseAgent`
- `MetricsAgent`

If too many key evidence agents degraded or produced no effective evidence, the judge path will be forced into one of these states:

- `insufficient_evidence`
- retry-failed-agents recommendation
- human review recommendation for governed deployments

The final payload can still summarize the current hypothesis, but it must not look like a normal high-signal conclusion.

### 4. Tool-disabled behavior

When the main command explicitly requests evidence retrieval but the corresponding tool is disabled, the agent should not present itself as having completed the requested investigation.

Instead it should return:

- `evidence_status=missing`
- `tool_status=disabled`
- next check instructions

This is especially important for:

- `LogAgent`
- `CodeAgent`
- `DatabaseAgent`

### 5. Frontend event-flow slimming

The incident detail page will stop using the raw realtime event stream as the primary UI source for dialogue rendering.

Changes:

- `llm_stream_delta`, `llm_http_request`, `llm_http_response`, `llm_call_started`, and similar low-level events stay out of the main dialogue list;
- only aggregated process events remain in the main analysis tabs;
- event ingestion becomes buffered/batched instead of immediate `setState` per message;
- timeline rendering is capped and segmented to reduce repeated full-array scans.

The raw events still remain available in detailed audit views, but not in the main interactive path.

### 6. Prompt slimming

Prompt reduction will focus on repeated boilerplate and oversized context blocks:

- shrink repeated output protocol text;
- reduce dialogue/history slices per agent;
- trim commander/supervisor context payloads;
- keep structured output requirements but reduce duplicated instructions.

This is a secondary optimization after runtime and UI fixes.

## Validation

For the incident path represented by `inc_b3c54885`, the fix is acceptable when:

- key evidence agents do not all hit queue timeout in the same wave;
- the frontend remains responsive while the run is active;
- degraded agents are labeled as degraded/missing evidence rather than successful replies;
- final judgment clearly reflects evidence coverage and does not overstate confidence;
- targeted backend and frontend tests pass.
