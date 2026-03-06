# Governance And Benchmark SRE Redesign

## Background

The current `治理中心` and `评测中心` pages are difficult for ordinary SRE users to understand.

The problem is not missing data. The problem is that both pages expose backend capability buckets before they explain:

- who should use the page
- when the page should be opened
- what the first thing to look at is
- what action the user should take next

From the current frontend implementation:

- `治理中心` mixes system card, quality trend, runtime strategy, team metrics, feedback, remediation, external sync, and session replay in one long page: [/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx)
- `评测中心` is currently a thin benchmark runner and result viewer, but it does not explain how to interpret quality signals: [/Users/neochen/multi-agent-cli_v2/frontend/src/pages/BenchmarkCenter/index.tsx](/Users/neochen/multi-agent-cli_v2/frontend/src/pages/BenchmarkCenter/index.tsx)

The target user for this redesign is the on-call or duty SRE.

That means both pages should answer one core question quickly:

`Can I trust the current system behavior, and what should I do next?`

## Design Goal

Make both pages understandable to a new SRE in under 2 minutes.

The intended first-read path is:

1. Understand what the page is for.
2. See whether current status is healthy, risky, or degraded.
3. Identify the most important next action.
4. Expand into evidence, history, and control actions only if needed.

## Design Principles

### 1. Explain the page before exposing controls

Each page must start with:

- page purpose
- intended user
- when to use it
- the primary questions the page answers

### 2. Put judgment before detail

SRE users should first see:

- health summary
- quality summary
- active risk
- recommended next action

They should not first see raw lists or long control panels.

### 3. Separate read mode from action mode

Every page should clearly separate:

- `看状态`
- `看趋势`
- `做动作`
- `查明细`

### 4. Use progressive disclosure

Advanced operations such as strategy switching, remediation approval, external sync, and A/B eval must remain available, but they should appear after the user understands system state.

## Current Problems

## Governance Center Problems

### Problem 1: The page title does not explain the page

`治理中心` is a platform-builder term.

An SRE does not immediately know whether this page is for:

- viewing system health
- changing runtime policy
- approving changes
- replaying sessions

### Problem 2: No primary judgment area

The current page starts with a title card and three statistics, but none of them clearly answer:

- is the system stable
- is analysis quality falling
- are there pending risks

### Problem 3: Strong actions are mixed with weak context

Actions such as:

- switching runtime strategy
- approving remediation
- writing external sync records

are presented in the same visual weight as descriptive lists and metadata.

This makes the page feel like an internal admin console instead of an SRE control surface.

## Benchmark Center Problems

### Problem 1: The page is action-first, not interpretation-first

The first CTA is `运行 Benchmark`, but the page does not explain:

- when an SRE should run benchmark
- what constitutes good or bad quality
- how benchmark results relate to incident analysis trust

### Problem 2: Metrics lack narrative

Metrics such as:

- Top1 命中率
- 平均重叠分
- 超时率
- 空结论率

are shown without simple interpretation.

For a new SRE, this is a dashboard of numbers without operational meaning.

### Problem 3: History is passive

The history list shows generated baselines, but not:

- whether quality is improving or regressing
- whether the latest run is safe enough to trust
- what should be investigated next

## Target Page Model

The redesign keeps both routes and APIs, but changes the information architecture.

## 1. Governance Center becomes `系统治理与运行控制`

### Page purpose

This page tells the SRE:

- whether the multi-agent system is currently safe to trust
- whether runtime strategy is reasonable
- whether there are pending operational risks
- what controlled actions are available

### First screen structure

#### A. Hero explanation card

Contents:

- page title: `系统治理与运行控制`
- one-sentence description
- suitable audience: `值班 SRE / 平台治理负责人`
- three plain-language questions:
  - 当前系统是否可信
  - 当前策略是否过于激进或保守
  - 是否有待处理的治理动作

#### B. Critical status strip

Show 4 to 6 high-signal summary cards:

- 当前运行策略
- 最近质量趋势结论
- 待处理修复动作数
- 最近团队超时风险
- 自动同步状态
- Session 回放可用性

Each card should show:

- current value
- short interpretation
- state color: normal / warning / risk

#### C. Recommended next action card

One compact panel that summarizes the most important operational suggestion, for example:

- `最近 7 天 timeout rate 升高，建议先查看团队治理指标`
- `存在高风险修复提案未审批，建议先进入修复动作区确认`

This gives the page a clear entry point for new users.

### Second screen structure

Use tabs or segmented sections:

- `状态总览`
- `运行策略`
- `治理动作`
- `回放与审计`

#### 状态总览

Includes:

- system boundaries and safety controls
- team governance metrics
- token cost trend
- timeout hotspots
- tool failure hotspots

This area is for understanding current trust level.

#### 运行策略

Includes:

- current active profile
- profile selector
- strategy descriptions in human-readable language

Change from raw parameter list to interpreted summary:

- `balanced`: 默认值班策略，兼顾速度与覆盖
- `conservative`: 更保守，减少回合和工具消耗
- `aggressive`: 更激进，适合复杂疑难问题

The raw numeric fields can remain in a collapsed detail block.

#### 治理动作

Includes:

- feedback submission
- learning candidates
- remediation proposal / approval / execution / rollback
- external sync controls

This entire section should visually read as an action area:

- action cards
- clear CTA buttons
- pending item lists

#### 回放与审计

Includes:

- session replay input and output
- key decisions
- rendered steps

This section should look like a guided replay tool, not a generic form.

## 2. Benchmark Center becomes `分析质量评测`

### Page purpose

This page tells the SRE:

- whether recent analysis quality is stable
- whether a new run shows regression
- whether the current model or strategy should still be trusted

### First screen structure

#### A. Hero explanation card

Contents:

- page title: `分析质量评测`
- one-sentence description
- suitable audience: `值班 SRE / 平台治理负责人`
- plain-language questions:
  - 最近质量是否变差
  - 当前空结论和超时是否可接受
  - 新一次 benchmark 是否值得复盘

#### B. Quality judgment strip

Show 4 to 5 critical cards:

- Top1 命中率
- 平均重叠分
- 超时率
- 空结论率
- 最近一次运行耗时 or 样本规模

Each card should include a short interpretation:

- `高于最近基线`
- `接近风险阈值`
- `需要关注`

#### C. Run benchmark action card

Put the run controls inside one clear action card:

- sample count
- timeout seconds
- run button
- short explanation of when to run benchmark

This changes the user experience from `raw form` to `intentional operation`.

### Second screen structure

Use tabs or segmented sections:

- `结果总览`
- `样本明细`
- `历史趋势`

#### 结果总览

Includes:

- latest summary metrics
- last run status
- plain-language interpretation

If `lastRun` exists, the page should explicitly label it:

- `本次运行结果`
- `对比最近基线`

#### 样本明细

Includes:

- cases table
- status tags
- overlap score
- duration
- predicted root cause

The table should be framed as evidence for quality judgment, not as the whole page.

#### 历史趋势

Includes:

- baseline history
- trend summary
- visible regression cues

If charting is not added in this round, the list should still be rewritten with stronger semantics:

- latest baseline
- best recent baseline
- regression suspicion

## Visual Direction

The current frontend already uses a light, glass-like enterprise surface. This redesign should preserve the existing shell but improve hierarchy.

### Shared visual rules

- Large explanatory hero card at the top
- Compact status cards with clear semantic color
- Section titles written as user tasks, not backend modules
- Strong separation between `阅读区` and `操作区`
- Long raw lists placed lower and visually softened

### Color semantics

- blue: neutral system information
- green: healthy / safe
- amber: watch / degraded
- red: risk / pending action

### Typography semantics

- page title answers the purpose
- section subtitle answers `why this block matters`
- helper text explains operational meaning, not internal implementation

## Interaction Model

## Governance Center interaction flow

1. User enters page.
2. Reads hero explanation and status strip.
3. Sees one recommended next action.
4. Opens one of:
   - `状态总览`
   - `运行策略`
   - `治理动作`
   - `回放与审计`
5. Performs action only after understanding current state.

## Benchmark Center interaction flow

1. User enters page.
2. Reads hero explanation and quality judgment strip.
3. Decides whether the current quality is trustworthy.
4. If needed, runs benchmark from a dedicated action card.
5. Reviews:
   - overview first
   - sample details second
   - history trend last

## Content To Demote Or Hide

The following items should remain available but should not dominate the first screen:

- full raw system card boundaries list
- long runtime profile parameter strings
- full external sync mapping JSON
- full feedback item list
- long historical baseline list without interpretation

These belong in lower sections, collapsed panels, or secondary tabs.

## Implementation Strategy

Keep the existing backend APIs and route paths.

This redesign is frontend-only in scope:

- no route removal
- no backend contract change
- no data model change

The work should focus on:

- page framing
- sectioning
- language rewrite
- card hierarchy
- CTA placement
- visual rhythm

## Success Criteria

The redesign is successful if:

1. A first-time SRE can explain what each page is for in one sentence.
2. The first screen of each page answers `current status + next action`.
3. Strong actions no longer compete visually with low-signal metadata.
4. The pages feel like operational control surfaces, not internal admin dumps.
5. Existing backend capabilities remain accessible without needing backend changes.
