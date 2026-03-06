# Frontend Information Architecture Redesign

## Background

Current frontend structure is difficult for new users to understand.

The main problems are:

- Too many top-level entries in the left navigation.
- Several pages represent internal platform capabilities rather than end-user tasks.
- The main analysis page mixes orchestration state, evidence, assets, governance signals, raw event streams, and remediation suggestions in one oversized page.
- Users must understand the system architecture before they can complete the first useful action.

From the current codebase:

- Top-level navigation currently exposes 9 first-level routes: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/components/common/Sider/index.tsx)
- The main analysis page is oversized and acts as multiple products in one: [index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx)
- Governance, assets, tools, workbench, benchmark, history, settings all compete as peers from the first screen: [App.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/App.tsx)

## Design Goal

Make the product understandable for a first-time user in under 5 minutes.

The target user journey is:

1. Enter the product.
2. Find incidents or start one analysis.
3. Open one incident.
4. Follow a stable detail layout: summary, timeline, evidence, ownership, result.
5. Use advanced pages only when necessary.

## Industry Pattern Summary

The redesign follows common incident-analysis product patterns used by major observability and incident-response tools.

Shared characteristics:

- Queue first, detail second.
- Incident detail is the primary workspace.
- Timeline is the spine of the investigation.
- Advanced governance and automation are not first-class entry points for ordinary users.
- Settings, integrations, benchmarking, and experimentation are separated from the primary task flow.

## Current Information Architecture Problems

### Problem 1: Top-level navigation represents implementation domains, not user tasks

Examples:

- `调查工作台`
- `评测中心`
- `治理中心`
- `工具中心`

These names make sense to platform builders, but not to the first-time operator trying to analyze an incident.

### Problem 2: The product lacks a clear primary surface

A user should immediately understand which page is the default operating page.

Right now that is unclear because:

- Home is a dashboard.
- Incident is an execution page.
- History is another list page.
- Workbench is another investigation page.
- Governance is another operational page.

This creates product overlap and splits user attention.

### Problem 3: Incident detail page violates progressive disclosure

The incident page currently exposes too much raw system behavior at once.

This is useful for experts, but confusing for most users.

The page should separate:

- What happened
- What the system is doing now
- What evidence supports the conclusion
- Who owns the fault domain
- What the next action is

## Target Information Architecture

### Top-level navigation

The first-level navigation should be reduced to 5 entries:

- `首页`
- `事件`
- `责任田`
- `设置`
- `高级`

### Navigation mapping from current routes

- `/` remains `首页`
- `/incident` and `/history` collapse into `事件`
- `/assets` remains `责任田`
- `/settings` remains `设置`
- `/workbench`, `/benchmark`, `/governance`, `/tools` move under `高级`

### Advanced section contents

`高级` should contain secondary navigation or tabs:

- `回放与审计`
- `治理`
- `评测`
- `工具接入`

This keeps the capabilities but removes them from the default mental model.

## Target Page Model

### 1. Home

Purpose:

- Explain what the system does.
- Offer one clear primary action.
- Show only the minimum useful status summary.

Primary actions:

- `新建分析`
- `查看事件队列`

Home should stop acting as a dense feature catalog.

### 2. Event Queue

This becomes the main operating entry.

It replaces the current split between `故障分析` and `历史记录`.

The queue page should support:

- List of incidents
- Filter by status, severity, service, owner
- Start analysis
- Resume analysis
- Open detail

This page answers:

- What needs attention now
- Which incidents are running
- Which incidents are done

### 3. Incident Detail

This is the core product page and should be structured as a stable investigation layout.

Recommended tabs:

- `概览`
- `时间线`
- `证据`
- `责任田`
- `结论与行动`

Recommended header block:

- Incident title
- Severity
- Current status
- Current phase
- Responsible team / owner
- Confidence
- Main CTA buttons

### 4. Responsibility Assets

Keep this as a first-level page because it is a product differentiator.

But the page should present two clear modes:

- `资产维护`
- `责任田定位`

The current mixed page already has both concepts, but they should be visually separated and simplified.

### 5. Settings

Keep only operator configuration here:

- model and runtime settings
- tool routing config
- skill routing config
- external data source config

This page should not also act as a product operations center.

### 6. Advanced

This area is explicitly for expert and platform roles.

Sections:

- `回放与审计`
- `治理`
- `评测`
- `工具接入`

The purpose is to protect novice users from platform internals while keeping platform capabilities available.

## Incident Detail Layout

### Overview tab

Show only the most important information:

- Symptom summary
- Current execution status
- Root cause summary if available
- Confidence
- Responsible domain / aggregate / team
- Key action recommendations

This tab is for fast comprehension.

### Timeline tab

The timeline should become the default investigation narrative.

It should merge:

- phase changes
- asset mapping milestones
- agent milestones
- retries / failures
- final result emission

The user should be able to answer:

- What happened first
- Where the flow is currently blocked
- Which step produced the conclusion

### Evidence tab

This tab should normalize different evidence sources into one evidence-oriented view:

- log evidence
- code evidence
- DB evidence
- metric evidence
- rule / runbook references

Evidence should be grouped by source and strength, not by backend event type.

### Responsibility tab

Show:

- matched domain
- aggregate
- owner team
- owner
- matched interfaces
- code artifacts
- DB tables

This tab should expose the responsibility mapping as a business ownership answer, not as a raw internal payload.

### Result and Action tab

Show:

- final root cause
- candidate causes
- dissenting opinions
- verification plan
- remediation proposal / action items

This is where the user decides what to do next.

## Interaction Principles

### Principle 1: One primary action per screen

Examples:

- Home: start or view queue
- Event queue: open or start analysis
- Incident detail: understand and act
- Assets: maintain or locate

### Principle 2: Prefer business language over internal architecture language

Bad labels:

- 调查工作台
- 工具中心
- 治理中心

Better labels:

- 事件
- 回放与审计
- 平台治理
- 工具接入

### Principle 3: Progressive disclosure

Default view should show interpretation.

Advanced sections should reveal:

- raw events
- audit payloads
- lineage details
- internal strategy parameters

### Principle 4: Stable detail anatomy

Every incident should have the same visual structure.

Users should not need to re-learn the page for each case.

## What Should Move Out of the Main Flow

The following should not stay in the novice primary flow:

- A/B evaluation
- runtime strategy tuning
- tenant policy editing
- external sync records
- tool registry operations
- governance feedback experiments

These are platform governance functions, not first-line incident operations.

## Non-Goals

This redesign does not change:

- backend RCA orchestration logic
- skill routing logic
- governance business rules
- remediation workflow semantics

This redesign is about product structure and clarity, not runtime architecture.

## Success Criteria

The redesign is successful if:

- New users can tell where to start without explanation.
- Incident detail becomes the clear primary working surface.
- Advanced platform functions remain available but no longer compete with core analysis flow.
- Page labels align with user goals rather than internal implementation concepts.
- The number of first-level navigation decisions drops sharply.

## Recommended Implementation Order

1. Reduce top-level navigation and reclassify pages.
2. Merge incident list and history mental model into a single event queue.
3. Refactor incident page into a tabbed detail layout.
4. Move governance, benchmark, tools, and workbench into advanced navigation.
5. Simplify home page to one CTA-driven landing page.

