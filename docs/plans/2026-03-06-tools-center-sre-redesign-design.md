# Tools Center SRE Redesign

## Background

The current `工具中心` page exposes real capabilities, but it is organized as a platform utility page instead of an SRE-facing tool trust page.

Today the page shows:

- tool registry list
- tool detail and connector mapping
- connector actions
- trial run
- session-level audit
- output reference preview

The problem is that these blocks appear as peers.

For an SRE, the first question is not `how do I connect or call a connector`.

The first questions are:

- which tools are currently available
- which connectors are unhealthy
- should I trust the current tool results for this session

The page should answer those first.

## Design Goal

Make the tools page useful for both:

- on-call SRE
- platform operator

But default the reading order to SRE concerns:

1. tool trust and health
2. connector and trial actions
3. session audit and full output detail

## Design Principles

### 1. Health first, configuration second

The page should first show:

- tool availability
- connector health
- whether a session audit exists

### 2. Let users judge before they act

Connection, disconnection, trial run, and direct tool calls are still necessary, but they should appear after the user understands current state.

### 3. Keep technical depth available

Raw output preview and full audit logs remain important, but they should not dominate the first screen.

## Target Page Structure

## 1. Hero explanation card

Title:

- `工具健康与接入控制`

Purpose:

- explain when an SRE should visit this page

Question tags:

- 当前哪些工具可用
- 哪些连接器不稳定
- 当前 session 的工具结果值不值得信任

## 2. Tool health summary strip

Show high-signal cards for:

- total tools
- enabled tools
- mapped connectors
- unhealthy connectors
- session audit state
- selected tool status

This gives SREs an immediate trust snapshot.

## 3. Recommended next action

Derived from:

- unhealthy connectors
- no selected tool
- no audit loaded
- no trial result

Possible guidance:

- inspect unhealthy connectors
- run a trial
- inspect session audit

## 4. Main tabs

### Tab A: `工具总览`

Contains:

- tool registry list
- selected tool detail
- connector mappings

This answers:

- what tools exist
- who owns them
- whether the current selected tool is usable

### Tab B: `连接与试跑`

Contains:

- connector control actions
- tool trial runner

This answers:

- can I connect, disconnect, and exercise the tool safely

### Tab C: `会话审计`

Contains:

- session-level tool audit
- session id input

This answers:

- should I trust the tool activity in a concrete session

### Tab D: `输出引用`

Contains:

- output reference preview

This answers:

- what was the complete tool output behind a truncated or referenced record

## Visual Direction

Reuse the same advanced operational page primitives:

- hero card
- summary cards
- recommendation card
- lower-priority detail blocks

This keeps advanced pages consistent.

## Non-Goals

This redesign does not:

- add new backend health checks
- change tool audit contracts
- redesign connector APIs

## Success Criteria

The redesign succeeds if:

1. An SRE can tell whether tool state is trustworthy from the first screen.
2. A platform operator can still perform connection and trial actions without extra clicks.
3. Session audit and output preview remain available but no longer dominate the top of the page.
