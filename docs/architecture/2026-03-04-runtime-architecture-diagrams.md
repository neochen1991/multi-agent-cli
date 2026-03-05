# 生产问题根因分析系统架构图（代码对齐版）

本文档用于固化架构图源，便于后续同步更新 PPT 与技术文档。  
对齐代码基线：

- `backend/app/api/ws_debates.py`
- `backend/app/services/debate_service.py`
- `backend/app/runtime/langgraph_runtime.py`
- `backend/app/runtime/langgraph/builder.py`
- `backend/app/runtime/langgraph/phase_executor.py`
- `backend/app/runtime/langgraph/nodes/supervisor.py`
- `backend/app/services/agent_tool_context_service.py`

## 1. 系统总体架构（Container）

```mermaid
flowchart LR
    U["用户 / 值班SRE"] --> FE["Frontend (React + AntD)"]
    FE --> API["FastAPI REST API"]
    FE --> WS["WebSocket /ws/debates/:session_id"]

    WS --> WSM["DebateWebSocketManager"]
    API --> DS["DebateService"]
    WSM --> DS

    DS --> ORCH["LangGraphRuntimeOrchestrator"]
    ORCH --> AG["ProblemAnalysisAgent + Expert Agents"]
    AG --> TOOLS["AgentToolContextService"]

    TOOLS --> GIT["Git Repo Search"]
    TOOLS --> LOG["Local Log Reader"]
    TOOLS --> EXCEL["Domain Excel/CSV"]
    TOOLS --> EXT["Telemetry / CMDB Connector"]

    ORCH --> STORE["DebateRepository (file|memory)"]
    ORCH --> LINEAGE["lineage_recorder + tool_audit"]
    DS --> REPORT["report_generation_service"]
```

## 2. LangGraph 状态图（Node Topology）

```mermaid
flowchart TB
    START --> init_session
    init_session --> round_start
    round_start --> supervisor_decide

    supervisor_decide --> analysis_parallel_node
    supervisor_decide --> analysis_collaboration_node
    supervisor_decide --> speak_agent_node["speak:<agent>_node"]
    supervisor_decide --> round_evaluate
    supervisor_decide --> finalize

    analysis_parallel_node --> supervisor_decide
    analysis_collaboration_node --> supervisor_decide
    speak_agent_node --> supervisor_decide

    round_evaluate -->|continue_next_round=true| round_start
    round_evaluate -->|continue_next_round=false| finalize
    finalize --> END
```

说明：

- `analysis_collaboration_node` 仅在 `DEBATE_ENABLE_COLLABORATION=true` 时加入。
- `speak:<agent>_node` 为动态节点，来自 `agent_sequence()` 与 `supervisor_step_to_node()` 映射。

## 3. 运行时序图（Frontend -> WS -> Debate -> Runtime）

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant WS as WSManager
    participant DS as DebateService
    participant LG as LangGraphRuntime
    participant AG as Agents/Tools

    FE->>WS: connect /ws/debates/:session_id?auto_start=true
    WS-->>FE: snapshot
    WS->>DS: execute_debate(session_id)
    DS->>LG: orchestrator.execute(context, event_callback)

    LG->>LG: GraphBuilder.build().compile()
    LG->>AG: supervisor_decide -> agent nodes
    AG-->>LG: evidence / tool result / chat message
    LG-->>WS: event (phase_changed, agent_chat, tool_io...)
    WS-->>FE: event stream

    LG-->>DS: final_payload
    DS-->>WS: result_ready
    WS-->>FE: result
```

## 4. Agent 工具调用链路（命令门禁）

```mermaid
flowchart LR
    CMD["ProblemAnalysisAgent command"] --> GATE["command_gate: allow_tool?"]
    GATE -->|deny| FALLBACK["skip tool, default analysis"]
    GATE -->|allow| TOOL["Tool execute"]
    TOOL --> AUDIT["audit_log + io_trace + permission_decision"]
    AUDIT --> MSG["agent feedback/evidence message"]
    MSG --> SUP["supervisor_decide / round_evaluate"]
```

说明：

- 工具调用受主 Agent 命令与工具开关双重约束。
- 审计信息由后端事件流透出，前端可查看摘要与完整引用信息。
