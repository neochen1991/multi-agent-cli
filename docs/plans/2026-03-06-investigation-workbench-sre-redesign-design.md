# Investigation Workbench SRE Redesign

## Background

The current `调查工作台` page exposes many useful runtime data sources, but it is still organized around technical data buckets instead of SRE replay tasks.

From the current implementation:

- session loading, filters, report comparison, lineage timeline, tool audit, decisions, evidence refs, and report diff are all presented as peers
- the page expects the user to already understand the meaning of lineage, replay, tool audit, and report versions
- the first screen does not clearly answer:
  - what this session concluded
  - why it concluded that way
  - which part of the trajectory should be checked first

For an on-call SRE, this makes the page feel like a debugging console rather than a replay workspace.

## Design Goal

Turn `调查工作台` into a replay-first page:

- first explain the final conclusion and current confidence
- then show the most important next inspection target
- then allow the user to drill into decisions, evidence, tools, reports, and raw audit details

The page should remain useful for deep audit, but that should become secondary.

## Target User

Primary user:

- on-call SRE

Secondary user:

- platform engineer or governance owner doing deep investigation

## Design Principles

### 1. Replay first, audit second

The page should first answer:

- what happened
- why it happened
- what is suspicious

Only after that should it show raw audit detail.

### 2. Put the session conclusion above the raw trace

The first screen should summarize:

- session state
- root cause
- confidence
- cross-source evidence status
- decision count
- tool call count

### 3. Guide the user to one next step

The page should derive one recommendation based on current data, such as:

- inspect report diff first
- inspect decisions first
- inspect tools first

### 4. Use tabs to separate intent

The current data blocks should be reorganized by replay task:

- replay overview
- decisions
- evidence and tools
- report comparison
- raw audit

## Target Page Structure

## 1. Hero explanation card

Purpose:

- explain what this page is for
- explain when an SRE should use it

Contents:

- title: `调查复盘台`
- one-sentence purpose
- audience tags
- three plain-language questions:
  - 这次 session 最终怎么判
  - 为什么这么判
  - 哪一步最值得怀疑

## 2. Load and filter strip

Keep:

- session id input
- load button
- phase filter
- agent filter
- incident id input
- report compare button

But visually separate it from the hero so the page reads as:

- understand page
- load session
- inspect replay

## 3. Summary strip

Show high-signal cards for:

- 会话状态
- 根因结论
- 置信度
- 关键决策数
- 工具调用数
- 报告版本数

These cards should summarize whether the replay is stable or suspicious.

## 4. Recommended next action

Derived from existing data:

- if report diff exists, inspect report comparison
- if confidence is low or cross-source evidence failed, inspect key decisions
- if tool audit count is high, inspect evidence and tools
- otherwise inspect replay overview

## 5. Main tabs

### Tab A: `复盘总览`

Contains:

- root cause summary
- confidence and cross-source status
- evidence chain
- first several replay steps

This tab is the default replay reading surface.

### Tab B: `关键决策`

Contains:

- key decisions
- timeline
- current filters

This tab answers:

- why the system reached the current conclusion

### Tab C: `证据与工具`

Contains:

- evidence refs
- tool audit records

This tab answers:

- what evidence the conclusion used
- whether tools behaved as expected

### Tab D: `报告对比`

Contains:

- report diff summary
- report versions table

This tab answers:

- whether multiple generated reports diverged in meaningful ways

### Tab E: `原始审计`

Contains:

- lineage records
- raw replay details

This tab is explicitly for deep technical audit and should be visually marked as secondary.

## Visual Direction

Reuse the same operational page pattern introduced for governance and benchmark pages:

- explanatory hero
- summary cards
- recommendation card
- softer detail sections

This keeps the entire advanced area visually coherent.

## Non-Goals

This redesign should not:

- change backend APIs
- change replay or lineage data contracts
- add new persistence
- add new charts unless already supported cheaply

## Success Criteria

The redesign succeeds if:

1. A first-time SRE can explain what the page is for in one sentence.
2. The first screen shows conclusion, confidence, and next inspection target.
3. Deep audit remains available without dominating the default reading path.
4. Existing replay, tool audit, and report comparison capabilities remain intact.
