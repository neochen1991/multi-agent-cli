# ImpactAnalysisAgent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated `ImpactAnalysisAgent` that analyzes blast radius from incident text, logs, alerts, responsibility mapping, and peer evidence, then outputs affected functions, affected interfaces, and measured/estimated user impact.

**Architecture:** Keep the current LangGraph runtime and multi-agent contracts intact, add `ImpactAnalysisAgent` as an analysis-phase expert, extend structured expert output and Judge impact payloads in an additive-compatible way, and surface its results in the current frontend without breaking existing `impact_analysis` consumers.

**Tech Stack:** FastAPI, LangGraph runtime, Python structured schemas/parsers, React + TypeScript frontend, pytest.

---

### Task 1: Register The New Agent In Docs And Runtime Contracts

**Files:**
- Modify: `docs/agents/agent-catalog.md`
- Modify: `docs/agents/protocol-contracts.md`
- Modify: `backend/app/runtime/langgraph/prompts.py`
- Modify: `backend/app/runtime/langgraph/state.py`
- Test: `backend/tests/test_runtime_message_flow.py`

**Step 1: Write the failing test**

Add a regression proving the runtime can recognize `ImpactAnalysisAgent` as a first-class analysis expert and that its structured output shape includes function-level, interface-level, and user-impact sections.

**Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py -q
```

**Step 3: Write minimal implementation**

Implement:
- `ImpactAnalysisAgent` entry in the agent catalog docs
- prompt/schema definition for its structured output
- any required additive state contract updates
- short Chinese comments on all new schema helpers

**Step 4: Run targeted tests**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py backend/tests/test_judge_payload_recovery.py -q
```

**Step 5: Commit**

```bash
git add docs/agents/agent-catalog.md docs/agents/protocol-contracts.md backend/app/runtime/langgraph/prompts.py backend/app/runtime/langgraph/state.py backend/tests/test_runtime_message_flow.py backend/tests/test_judge_payload_recovery.py
git commit -m "feat: register impact analysis agent contracts"
```

### Task 2: Wire ImpactAnalysisAgent Into Runtime Scheduling And Context

**Files:**
- Modify: `backend/app/runtime/langgraph_runtime.py`
- Modify: `backend/app/runtime/langgraph/builder.py`
- Modify: `backend/app/runtime/langgraph/nodes/agents.py`
- Modify: `backend/app/runtime/langgraph/routing/rules_impl.py`
- Modify: `backend/app/services/agent_skill_service.py`
- Modify: `backend/app/services/agent_tool_context_service.py`
- Test: `backend/tests/test_runtime_message_flow.py`
- Test: `backend/tests/test_langgraph_route_guardrail.py`

**Step 1: Write the failing test**

Add a regression proving:
- `ProblemAnalysisAgent` can issue commands to `ImpactAnalysisAgent`
- the new expert receives responsibility mapping and peer evidence context
- `quick/standard` routing invokes it only in supported conditions

**Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py backend/tests/test_langgraph_route_guardrail.py -q
```

**Step 3: Write minimal implementation**

Implement:
- agent registration in the runtime sequence / builder wiring
- focused context injection for incident text, alert signals, responsibility mapping, API endpoints, service names, and peer evidence
- routing rules that decide when to run the new expert
- short Chinese comments on all new runtime/routing helpers

**Step 4: Run targeted tests**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py backend/tests/test_langgraph_route_guardrail.py backend/tests/test_agent_tool_context_service.py backend/tests/test_agent_skill_service.py -q
```

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph_runtime.py backend/app/runtime/langgraph/builder.py backend/app/runtime/langgraph/nodes/agents.py backend/app/runtime/langgraph/routing/rules_impl.py backend/app/services/agent_skill_service.py backend/app/services/agent_tool_context_service.py backend/tests/test_runtime_message_flow.py backend/tests/test_langgraph_route_guardrail.py backend/tests/test_agent_tool_context_service.py backend/tests/test_agent_skill_service.py
git commit -m "feat: wire impact analysis agent into runtime"
```

### Task 3: Normalize Judge And Result Payloads For Richer Impact Data

**Files:**
- Modify: `backend/app/runtime/langgraph/parsers.py`
- Modify: `backend/app/services/debate_service.py`
- Modify: `backend/app/services/report_generation_service.py`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/app/models/debate.py`
- Modify: `backend/app/api/debates.py`
- Test: `backend/tests/test_judge_payload_recovery.py`
- Test: `backend/tests/test_debate_service_effective_conclusion.py`
- Test: `backend/tests/test_report_generation_service.py`

**Step 1: Write the failing test**

Add regressions requiring final payloads to preserve old impact fields and also include additive detail fields:
- affected functions
- affected interfaces
- measured users
- estimated users
- estimation basis
- unknowns

**Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_report_generation_service.py -q
```

**Step 3: Write minimal implementation**

Implement:
- Judge payload normalization for richer `impact_analysis`
- additive Pydantic/API/report compatibility
- fallback shaping when only part of the impact structure is present
- short Chinese comments on all new normalization helpers

**Step 4: Run targeted tests**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_report_generation_service.py backend/tests/test_p0_incident_debate_report.py -q
```

**Step 5: Commit**

```bash
git add backend/app/runtime/langgraph/parsers.py backend/app/services/debate_service.py backend/app/services/report_generation_service.py backend/app/services/report_service.py backend/app/models/debate.py backend/app/api/debates.py backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_report_generation_service.py backend/tests/test_p0_incident_debate_report.py
git commit -m "feat: normalize rich impact analysis payloads"
```

### Task 4: Surface ImpactAnalysisAgent In The Frontend

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/Incident/index.tsx`
- Modify: `frontend/src/components/incident/DebateResultPanel.tsx`
- Modify: `frontend/src/v2/pages/IncidentV2.tsx`

**Step 1: Update API typings**

Extend frontend impact-analysis typings to carry:
- affected functions
- affected interfaces
- measured and estimated users
- estimation basis
- unknowns

**Step 2: Add process visibility**

Show `ImpactAnalysisAgent` in the incident process / expert stream with concise summaries for function impact, interface impact, and user-scope reasoning.

**Step 3: Add result rendering**

Render additive sections in the result area:
- 功能影响总览
- 接口影响明细
- 用户影响量化与估算依据

**Step 4: Manual verification**

Run:
```bash
npm run start:all
```

Verify:
- process area shows `ImpactAnalysisAgent`
- result area renders new impact sections
- old `affected_services / business_impact` display still works

**Step 5: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/pages/Incident/index.tsx frontend/src/components/incident/DebateResultPanel.tsx frontend/src/v2/pages/IncidentV2.tsx
git commit -m "feat: surface impact analysis agent in frontend"
```

### Task 5: Add Benchmarks And End-To-End Verification

**Files:**
- Create: `backend/tests/test_impact_analysis_agent.py`
- Modify: `backend/tests/test_runtime_message_flow.py`
- Modify: `backend/tests/test_judge_payload_recovery.py`
- Create or Modify benchmark fixture files under existing smoke/fixture directories as needed

**Step 1: Add benchmark-style fixtures**

Create at least one scenario covering:
- affected functions and interfaces are both inferable
- measured users are missing but estimated users are possible
- unknowns are explicitly listed

**Step 2: Run targeted backend tests**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_impact_analysis_agent.py backend/tests/test_runtime_message_flow.py backend/tests/test_judge_payload_recovery.py -q
```

**Step 3: Run smoke scenario**

Run:
```bash
SMOKE_SCENARIO=payment-timeout-upstream node ./scripts/smoke-e2e.mjs
```

Expected:
- `ImpactAnalysisAgent` appears in process trace
- final result contains enriched `impact_analysis`
- report generation remains successful

**Step 4: Final regression**

Run:
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_impact_analysis_agent.py backend/tests/test_runtime_message_flow.py backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_report_generation_service.py -q
```

**Step 5: Commit**

```bash
git add backend/tests/test_impact_analysis_agent.py backend/tests/test_runtime_message_flow.py backend/tests/test_judge_payload_recovery.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_report_generation_service.py
git commit -m "test: verify impact analysis agent"
```
