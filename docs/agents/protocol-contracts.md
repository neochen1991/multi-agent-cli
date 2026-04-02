# Agent Protocol Contracts

## 1. Scope

This document defines the minimum runtime contracts for agent-to-agent orchestration,
tool audit, skill audit, and final judgment output.

These contracts are normative for:
- runtime event emission
- lineage/replay rendering
- frontend investigation views
- future HITL and benchmark extensions

## 2. Session Config Protocol

### `debate_config_applied`

Purpose:
- records the effective session-level debate configuration after API defaults, execution mode, and runtime policy are merged

Required fields:
- `type`: `debate_config_applied`
- `execution_mode`
- `analysis_depth_mode`
- `max_rounds`

Constraints:
- must be emitted once the effective session config is known
- `analysis_depth_mode` must be one of `quick | standard | deep`
- explicit `max_rounds` overrides are allowed, but the event must still carry the resolved value
- `analysis_depth_mode` should affect runtime policy beyond round count when possible, including analysis agent coverage and discussion budget

## 3. Command Protocol

### `agent_command_issued`

Purpose:
- records that `ProblemAnalysisAgent` issued a structured command to a target agent

Required fields:
- `type`: `agent_command_issued`
- `commander`: source agent name, usually `ProblemAnalysisAgent`
- `target`: target agent name
- `loop_round`: current loop round
- `round_number`: user-facing round index
- `command.task`: concrete task
- `command.focus`: focus area
- `command.expected_output`: expected output shape

Constraints:
- must be emitted before target agent execution starts
- `target` must map to a registered agent
- command fields should be short, actionable, and non-empty when possible

### `ProblemAnalysisAgent` structured planning output

Purpose:
- records the planner-style dispatch decision emitted by `ProblemAnalysisAgent`

Required fields:
- `selected_agents`: agents chosen for the current step
- `commands`: structured commands aligned with `selected_agents`
- `next_mode`
- `should_stop`

Recommended fields:
- `next_agent`
- `analysis`
- `conclusion`
- `evidence_chain`
- `confidence`

Constraints:
- `selected_agents` should be the primary dispatch signal for the current step
- `commands.target_agent` should stay aligned with `selected_agents`
- runtime may trim `selected_agents` by `allowed_analysis_agents` and `max_parallel_agents`
- if `selected_agents` is absent, runtime may fall back to `commands` and then `next_agent` for compatibility

## 4. Feedback Protocol

### `agent_command_feedback`

Purpose:
- records the structured feedback from a target agent back to the commander

Required fields:
- `type`: `agent_command_feedback`
- `source`: agent returning feedback
- `target`: receiver, usually `ProblemAnalysisAgent`
- `loop_round`
- `round_number`
- `feedback`: summary of what was found

Recommended fields:
- `command`: the command being answered
- `confidence`: numeric confidence in range `[0, 1]`
- `status`: `ok | degraded | failed`

Constraints:
- should answer a previously issued command
- should be parseable without reading free-form transcript context

## 5. Peer Dialogue Protocol

### `agent_chat_message`

Purpose:
- records peer-to-peer or peer-to-supervisor conversational messages

Required fields:
- `type`: `agent_chat_message`
- `source`
- `target`
- `message`

Recommended fields:
- `reply_to`
- `loop_round`
- `round_number`

Constraints:
- should not replace structured command or feedback events
- free-form dialogue is supplementary, not the primary control channel

## 6. Tool Context Protocol

### `agent_tool_context_prepared`

Purpose:
- records the tool context, focused context, and command-gate decision prepared for an agent before tool execution

Required fields:
- `type`: `agent_tool_context_prepared`
- `agent_name`
- `tool_name`
- `status`
- `command_gate`

Recommended fields:
- `focused_preview`
- `data_preview`
- `execution_path`
- `permission_decision`

Constraints:
- should be emitted before an actual tool call or tool fallback
- must be consistent with the later tool IO / tool audit records
- focused previews should stay compact and avoid dumping raw payloads
- runtime prompts may consume the prepared result through an explicit context envelope:
  - `shared_context`
  - `focused_context`
  - `tool_context`
  - `peer_context`
  - `mailbox_context`
  - `work_log_context`
- expert prompts should render the envelope sections instead of dumping raw incident payloads
- `ImpactAnalysisAgent` 的结构化输出应优先包含：
  - `impact_summary.affected_functions`
  - `impact_summary.affected_interfaces`
  - `impact_summary.affected_user_scope`
  - `impact_summary.unknowns`
- `affected_user_scope` 需要区分：
  - `measured_users`: 已有明确证据支撑的量化值
  - `estimated_users`: 基于流量/失败率/时间窗/责任田范围的估算值
  - `estimation_basis`: 估算依据
  - `confidence`: 影响量化置信度

## 7. Tool Audit Protocol

### `tool_audit`

Purpose:
- records a tool call decision and execution result

Required fields:
- `type`: `tool_audit`
- `agent_name`
- `tool_name`
- `status`
- `duration_ms`

Recommended fields:
- `command_gate`
- `request_summary`
- `response_summary`
- `error`

Constraints:
- every tool invocation must be auditable
- request/response should be summarized to avoid log explosion

## 8. Skill Audit Protocol

### `skill_hit`

Purpose:
- records that a local skill was selected and injected into agent context

Required fields:
- `type`: `skill_hit`
- `agent_name`
- `skill_name`
- `skill_dir`
- `selection_source`

Recommended fields:
- `injection_summary`
- `matched_signals`

Constraints:
- every injected skill must be explainable
- full raw skill content should not be dumped into event logs

## 9. Final Judgment Contract

### `final_judgment`

Purpose:
- records the final structured RCA output, usually from `JudgeAgent`

Required fields:
- `root_cause.summary`
- `root_cause.category`
- `root_cause.confidence`
- `evidence_chain`
- `root_cause_candidates`
- `evidence_coverage`

Recommended fields:
- `claim_graph.primary_claim`
- `claim_graph.supports`
- `claim_graph.contradicts`
- `claim_graph.missing_checks`
- `claim_graph.eliminated_alternatives`
- `action_items`
- `responsible_team`
- `responsible_owner`
- `verification_plan`
- `convergence_score`
- `round_gap_summary`
- `evidence_coverage.weighted_score`
- `evidence_coverage.corroboration_count`

Constraints:
- if effective conclusion gate is enabled, placeholder conclusions are invalid
- output must remain machine-readable
- `root_cause_candidates` should preserve ranking information for Top-K rendering
- `evidence_coverage` should remain compatible with `ok / degraded / missing`
- `claim_graph` is additive metadata and must not replace legacy `evidence_chain`
- `claim_graph.primary_claim` should align with `root_cause`
- `claim_graph.supports / contradicts / missing_checks / eliminated_alternatives` should stay list-shaped for benchmark and governance consumers

## 10. Human Review Boundary Contract

### `human_review`

Purpose:
- records the pending-review state used by runtime finalize, result persistence, and resume flow

Required fields:
- `status`
- `reason`
- `payload`
- `resume_from_step`

Recommended fields:
- `requested_at`

Constraints:
- runtime waiting-review payloads should reuse the same structure in `session.context.human_review` and `final_payload.human_review`
- `resume_from_step` should default to `report_generation` when omitted
- human review metadata must stay additive and must not overwrite the final judgment body

## 11. Compatibility Rules

1. New fields may be added, but existing required fields must remain stable.
2. Frontend views should prefer structured fields over transcript parsing.
3. Benchmark and HITL extensions must build on these contracts rather than inventing parallel formats.
4. `analysis_depth_mode` and `max_rounds` are part of the stable session contract once a session is created.
