# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-Agent SRE Debate Platform - A production incident root cause analysis system using LangGraph multi-agent orchestration. The system coordinates multiple expert agents (Log/Domain/Code/Critic/Rebuttal/Judge) through multi-round debate to produce structured analysis reports.

**Tech Stack:**
- Backend: Python 3.11+ / FastAPI / LangGraph / LangChain
- Frontend: React 18 / TypeScript / Ant Design / Vite
- Storage: Local file or memory (no external database required)

## Common Commands

### Start/Stop Services
```bash
# Start both backend and frontend
npm run start:all

# Stop all services
npm run stop:all

# Force stop (release ports)
npm run stop:all:force
```

Services run at:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`

### Backend Development
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run server
python -m app.main

# Lint
ruff check backend/app backend/tests

# Run all tests
pytest -q backend/tests

# Run specific test file
pytest backend/tests/test_state_reducer.py -v
```

### Frontend Development
```bash
cd frontend
npm install

# Dev server
npm run dev

# Type check
npm run typecheck

# Build
npm run build
```

### E2E Smoke Test
```bash
node ./scripts/smoke-e2e.mjs
```

## Architecture

### Multi-Agent System

```
ProblemAnalysisAgent (Coordinator)
    ├── LogAgent      - Log evidence analysis
    ├── DomainAgent   - Interface to domain/responsibility mapping
    ├── CodeAgent     - Code path and risk analysis
    ├── CriticAgent   - Challenge and evidence gap identification
    ├── RebuttalAgent - Rebuttal and evidence reinforcement
    └── JudgeAgent    - Final ruling and recommendations
```

### Key Backend Paths

| Path | Purpose |
|------|---------|
| `backend/app/runtime/langgraph_runtime.py` | Runtime orchestration entry point |
| `backend/app/runtime/langgraph/` | Nodes, routing, state, executors |
| `backend/app/runtime/langgraph/state.py` | DebateExecState definition with typed reducers |
| `backend/app/services/debate_service.py` | Session execution and event handling |
| `backend/app/services/agent_tool_context_service.py` | Tool context, gate control, audit logging |
| `backend/app/api/ws_debates.py` | WebSocket endpoint for real-time events |
| `backend/app/config.py` | Configuration (LLM, storage, debate params) |

### Frontend Pages

- `/` - Home page
- `/incident` - Analysis page (asset mapping, debate process, results)
- `/history` - Historical records
- `/assets` - Asset view
- `/settings` - Tool and login configuration

### Data Flow

1. User creates Incident via API
2. Session created, WebSocket connects
3. `DebateService.execute_debate()` starts LangGraph runtime
4. ProblemAnalysisAgent coordinates task distribution
5. Expert agents execute (with optional tool calls)
6. Events streamed via WebSocket (`agent_chat`, `tool_io`, `phase`)
7. JudgeAgent produces final ruling
8. Report generated and stored

### State Management

The `DebateExecState` uses LangGraph-style annotated types with reducers:
- `history_cards` - Agent output cards for frontend display
- `agent_outputs` - Per-agent output dictionary
- `evidence_chain` - Global evidence chain
- `agent_commands` - Commander-issued task dictionary
- `agent_mailbox` - Inter-agent message bus

## Configuration

Main config: `backend/app/config.py`

Key environment variables:
- `LLM_BASE_URL` - OpenAI-compatible API endpoint
- `LLM_MODEL` - Model name (default: kimi-k2.5)
- `LLM_API_KEY` - API key
- `LOCAL_STORE_BACKEND` - `file` or `memory`
- `DEBATE_MAX_ROUNDS` - Maximum debate rounds (default: 1)

## Tool Integration

Expert agents can call external tools:
- `CodeAgent` - Git repository search
- `LogAgent` - Local log file reading
- `DomainAgent` - Responsibility Excel/CSV query

Tools require commander-issued commands with `use_tool` flag. Each call generates audit records.

## API Prefix

All API endpoints use `/api/v1` prefix. Key endpoints:
- `POST /incidents/` - Create incident
- `POST /debates/` - Create debate session
- `ws://localhost:8000/ws/debates/{session_id}` - WebSocket for real-time events
- `GET /reports/{incident_id}` - Get analysis report