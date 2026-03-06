# Advanced Dashboard And Lite Charts Design

## Background

The advanced area has now been simplified at the page level:

- governance explains system trust and control
- benchmark explains quality trust
- investigation explains replay and audit
- tools explains tool trust and connector health

However, the advanced landing page still does not tell users:

- which page to enter first
- which page matches which problem
- what the overall advanced-area state looks like

At the same time, the four pages still depend too much on text lists.

They are more understandable than before, but users still need to read too much text before spotting:

- degradation
- concentration of risk
- unusual distribution

## Design Goal

Build one advanced landing page that acts as a navigation cockpit, then add lightweight visual summaries to the four advanced pages without introducing a new charting library.

The result should make the advanced area feel like one coherent product:

1. choose the right page quickly
2. see small visual summaries quickly
3. dive into text detail only when necessary

## Constraints

- do not add new backend APIs
- do not add a new chart library
- use existing page data only
- prefer lightweight visual components such as:
  - progress bars
  - stacked stat rows
  - mini trend strips
  - segmented bars
  - simple ratio cards

## Part 1: Advanced Landing Page Redesign

## Page role

The advanced landing page should become a navigation cockpit.

It should answer:

- what kind of advanced task do I need right now
- which page should I enter first
- what does the overall advanced-area state look like

## Structure

### 1. Hero explanation card

Explain that the advanced area is for:

- governance
- quality verification
- replay and audit
- tools and connectors

The hero should explicitly tell the user:

- start from incident and history for normal work
- enter advanced only when deeper judgment or control is needed

### 2. `我现在要做什么` task grid

Four task cards:

- `判断系统现在是否可信` -> governance
- `判断最近质量是否退化` -> benchmark
- `复盘某次分析为什么这样判` -> workbench
- `判断工具和连接器是否可靠` -> tools

Each card should include:

- when to use
- what you will see first
- one primary CTA

### 3. `什么时候进哪一页` guidance strip

Short scenario mapping, for example:

- recent timeout or policy concern -> governance
- quality regression suspicion -> benchmark
- session replay need -> workbench
- tool trust issue -> tools

### 4. `当前平台状态摘要`

Show one small status card per advanced page, derived from existing page-level concepts:

- governance: strategy and pending risks
- benchmark: latest quality state
- workbench: replay and report diff entry hint
- tools: unhealthy connectors or no audit loaded

This does not need live cross-page API wiring if unavailable in this round.

It can be a descriptive dashboard shell using existing local page framing and clear CTA text.

## Part 2: Lightweight Visual Summaries

## Visual strategy

Do not add full charts.

Instead, use:

- horizontal progress bars
- stacked metric rows
- simple mini trend strips built with flex blocks
- compact legend chips

This keeps implementation cheap and consistent with the current enterprise UI.

## Governance Page Visuals

Add:

- team timeout distribution strip
- token cost trend mini bars
- tool failure hotspot emphasis

Purpose:

- make it obvious where risk concentrates

## Benchmark Page Visuals

Add:

- historical baseline quality strip
- timeout and empty-conclusion comparison bars
- last run vs latest baseline mini comparison

Purpose:

- let users see quality direction faster than reading file rows

## Investigation Workbench Visuals

Add:

- phase distribution or replay density strip
- key decisions vs tool calls vs timeline size ratio cards

Purpose:

- let users quickly see how heavy or suspicious a replay is

## Tools Page Visuals

Add:

- enabled vs disabled tools ratio bar
- healthy vs unhealthy connector ratio bar
- trial / audit readiness summary

Purpose:

- let users judge tool trust from a glance

## Shared Visual Pattern

Use one small reusable style family:

- `mini-chart-card`
- `mini-bar-list`
- `mini-ratio-bar`
- `mini-trend-strip`

These should be CSS-driven and data-light.

## Success Criteria

The redesign succeeds if:

1. Users can choose the correct advanced page from the landing page without guessing.
2. Each advanced page has at least one visual summary that reduces dependence on dense text lists.
3. No new chart dependency is introduced.
4. The advanced area reads as one coherent experience rather than several unrelated admin pages.
