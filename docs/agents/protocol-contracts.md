# Agent Protocol Contracts

## 1. Scope

This document defines the minimum runtime contracts for agent-to-agent orchestration,
tool audit, skill audit, and final judgment output.

These contracts are normative for:
- runtime event emission
- lineage/replay rendering
- frontend investigation views
- future HITL and benchmark extensions

## 2. Command Protocol

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

## 3. Feedback Protocol

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

## 4. Peer Dialogue Protocol

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

## 5. Tool Audit Protocol

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

## 6. Skill Audit Protocol

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

## 7. Final Judgment Contract

### `final_judgment`

Purpose:
- records the final structured RCA output, usually from `JudgeAgent`

Required fields:
- `root_cause.summary`
- `root_cause.category`
- `root_cause.confidence`
- `evidence_chain`

Recommended fields:
- `action_items`
- `responsible_team`
- `responsible_owner`
- `verification_plan`

Constraints:
- if effective conclusion gate is enabled, placeholder conclusions are invalid
- output must remain machine-readable

## 8. Compatibility Rules

1. New fields may be added, but existing required fields must remain stable.
2. Frontend views should prefer structured fields over transcript parsing.
3. Benchmark and HITL extensions must build on these contracts rather than inventing parallel formats.
