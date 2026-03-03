# Multi-Agent SRE Platform 改进方案

## 一、行业调研总结

### 1.1 主流多智能体框架对比

| 框架 | Stars | 核心特点 | 适用场景 | 架构模式 |
|------|-------|----------|----------|----------|
| **Dify** | 131k | 可视化工作流、低代码、全栈平台 | 快速原型、企业应用 | 工作流引擎 + RAG |
| **AutoGen** | 55.1k | 多Agent对话、人机协作、代码执行 | 复杂任务协作 | 分层架构 (Core/AgentChat/Extensions) |
| **CrewAI** | 45k | 角色扮演、自主Agent协作 | 团队协作场景 | Crew + Flow 双层架构 |
| **LangGraph** | 25.4k | 图编排、状态持久化、生产就绪 | 有状态长运行任务 | Pregel/Beam 启发的图计算 |
| **OpenAI Agents** | 19.2k | 轻量、Handoffs、Guardrails | OpenAI生态快速开发 | Agent + Handoff 模式 |
| **Langfuse** | 22.5k | LLM可观测性、Prompt管理 | 生产监控与调试 | Observability 平台 |

### 1.2 智能运维技术栈关键组件

```
┌─────────────────────────────────────────────────────────────┐
│                    智能运维全景架构                           │
├─────────────────────────────────────────────────────────────┤
│  监控层: Prometheus, Grafana, Datadog, Jaeger, ELK         │
│  数据层: 向量数据库(Pinecone/Milvus), 时序库, 日志存储       │
│  执行层: 沙箱环境(E2B), 工具调用(MCP), 代码执行              │
│  协作层: 多Agent编排(LangGraph/AutoGen/CrewAI)              │
│  应用层: 故障诊断、根因分析、自愈恢复、告警降噪               │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 核心技术趋势

1. **MCP (Model Context Protocol)**: 统一的工具调用协议，支持50+工具集成
2. **Agentic Workflow**: 从单一Agent到多Agent协作编排
3. **Human-in-the-Loop**: 人机协作成为标配
4. **Observability First**: 内置追踪和调试能力
5. **State Persistence**: 支持断点续传和长时间运行

---

## 二、本项目现状分析

### 2.1 当前架构优势
- ✅ LangGraph StateGraph 编排已采用
- ✅ 7个专家Agent角色分工明确
- ✅ WebSocket 实时事件推送
- ✅ 工具门控机制（Commander授权）
- ✅ 证据链追踪

### 2.2 现存问题（来自 MEMORY.md）

| 优先级 | 问题 | 影响 |
|--------|------|------|
| P0 | Agent定义重复 (AgentSpec vs AgentConfig) | 维护成本高，易出错 |
| P0 | ReAct Tools未集成到执行流 | 工具能力未释放 |
| P0 | 分析Agent串行执行 | 效率低下 |
| P1 | Supervisor路由逻辑散落4处 | 难以维护和扩展 |
| P1 | Graph构建硬编码 | 无法动态调整 |
| P1 | 无持久化Checkpointer | 无法恢复中断任务 |
| P2 | 缺乏可观测性集成 | 调试困难 |
| P2 | 无测试覆盖率统计 | 质量无保障 |

---

## 三、改进方案

### Phase 1: 架构重构 (Week 1-2)

#### 3.1.1 统一Agent定义

**参考**: OpenAI Agents SDK 的 `Agent` 类设计

```python
# 新的统一Agent定义 (参考 OpenAI Agents SDK)
@dataclass
class AgentDefinition:
    """统一的Agent定义，替代 AgentSpec 和 AgentConfig"""
    name: str
    instructions: str  # 系统提示词
    tools: list[Tool] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)  # 可移交给的其他Agent
    guardrails: list[Guardrail] = field(default_factory=list)
    model: str = "default"

    # 专家Agent特有
    expertise: str = ""  # 专业领域描述
    tool_permissions: list[str] = field(default_factory=list)  # 需要的工具权限
```

#### 3.1.2 并行执行优化

**参考**: AutoGen 的异步消息传递模式

```python
# backend/app/runtime/langgraph/parallel_executor.py
import asyncio
from typing import Any

class ParallelAnalysisExecutor:
    """并行分析执行器 - 替代串行执行"""

    async def execute_analysis_agents(
        self,
        agents: list[AgentDefinition],
        context: AnalysisContext
    ) -> dict[str, AgentOutput]:
        """并行执行多个分析Agent"""

        tasks = [
            self._execute_single_agent(agent, context)
            for agent in agents
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            agent.name: result
            for agent, result in zip(agents, results)
            if not isinstance(result, Exception)
        }
```

#### 3.1.3 动态图构建

**参考**: CrewAI 的 Flow 设计模式

```python
# backend/app/runtime/langgraph/dynamic_builder.py
class DynamicGraphBuilder:
    """动态图构建器 - 支持配置驱动的图结构"""

    def build_from_config(self, config: DebateConfig) -> StateGraph:
        """根据配置动态构建图"""
        graph = StateGraph(DebateExecState)

        # 动态添加节点
        for agent_config in config.agents:
            node_factory = self._get_node_factory(agent_config.type)
            graph.add_node(agent_config.name, node_factory.create(agent_config))

        # 动态添加边（从配置读取）
        for edge in config.edges:
            graph.add_edge(edge.source, edge.target)

        # 动态条件路由
        for router in config.routers:
            graph.add_conditional_edges(
                router.source,
                self._create_router(router),
                router.targets
            )

        return graph.compile(checkpointer=self.checkpointer)
```

### Phase 2: 工具生态集成 (Week 3-4)

#### 3.2.1 MCP工具集成

**参考**: OpenAI Agents SDK 的 MCP 支持

```python
# backend/app/tools/mcp_toolkit.py
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPToolkit:
    """MCP工具包 - 支持50+工具快速集成"""

    def __init__(self):
        self.sessions: dict[str, ClientSession] = {}

    async def connect_server(self, name: str, command: str, args: list[str]):
        """连接MCP服务器"""
        server = StdioServerParameters(command=command, args=args)
        async with stdio_client(server) as (read, write):
            session = ClientSession(read, write)
            await session.initialize()
            self.sessions[name] = session

    async def get_tools(self) -> list[Tool]:
        """获取所有已连接服务器的工具"""
        tools = []
        for session in self.sessions.values():
            response = await session.list_tools()
            tools.extend(self._convert_to_langchain_tool(t) for t in response.tools)
        return tools

# 预置MCP服务器配置
MCP_SERVERS = {
    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]},
    "puppeteer": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-puppeteer"]},
    "postgres": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-postgres"]},
    "prometheus": {"command": "npx", "args": ["-y", "@prometheus/mcp-server"]},
}
```

#### 3.2.2 ReAct工具执行器

```python
# backend/app/runtime/langgraph/react_executor.py
from langchain.agents import create_react_agent

class ReActToolExecutor:
    """ReAct工具执行器 - 集成到Agent执行流"""

    def __init__(self, agent: AgentDefinition, tools: list[Tool]):
        self.agent = agent
        self.react_agent = create_react_agent(
            llm=self._get_llm(agent.model),
            tools=tools,
            prompt=self._build_react_prompt(agent)
        )

    async def execute(self, state: DebateExecState) -> dict:
        """执行ReAct循环"""
        context = self._build_context(state)

        # ReAct循环: Thought -> Action -> Observation -> ...
        result = await self.react_agent.ainvoke(context)

        return {
            "agent_outputs": {self.agent.name: result},
            "history_cards": [self._create_history_card(result)]
        }
```

### Phase 3: 可观测性增强 (Week 5-6)

#### 3.3.1 Langfuse集成

```python
# backend/app/observability/langfuse_integration.py
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

class ObservabilityManager:
    """可观测性管理器 - 集成Langfuse"""

    def __init__(self):
        self.langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST
        )
        self.callback_handler = CallbackHandler()

    def trace_debate(self, session_id: str):
        """创建辩论追踪"""
        return self.langfuse.trace(
            id=session_id,
            name="debate_session",
            metadata={"project": "sre-debate-platform"}
        )

    def trace_agent_call(self, trace, agent_name: str, input_data: dict):
        """追踪Agent调用"""
        return trace.span(
            name=f"agent_{agent_name}",
            input=input_data,
            metadata={"agent": agent_name}
        )
```

#### 3.3.2 内置Tracing

```python
# backend/app/runtime/tracing.py
from dataclasses import dataclass, field
from datetime import datetime
import json

@dataclass
class ExecutionTrace:
    """执行追踪记录"""
    trace_id: str
    session_id: str
    agent_name: str
    start_time: datetime
    end_time: datetime | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    status: str = "running"
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "duration_ms": (self.end_time - self.start_time).total_seconds() * 1000 if self.end_time else None,
            "tokens": {"input": self.input_tokens, "output": self.output_tokens},
            "tool_calls": self.tool_calls,
            "status": self.status
        }
```

### Phase 4: 存储与持久化 (Week 7-8)

#### 3.4.1 Checkpointer持久化

**参考**: LangGraph 的 SqliteSaver / PostgresSaver

```python
# backend/app/runtime/checkpointer.py
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.postgres import PostgresSaver

class CheckpointManager:
    """检查点管理器 - 支持断点续传"""

    def __init__(self, backend: str = "sqlite"):
        if backend == "sqlite":
            self.saver = SqliteSaver.from_conn_string("checkpoints.db")
        elif backend == "postgres":
            self.saver = PostgresSaver.from_conn_string(settings.DATABASE_URL)

    async def save(self, thread_id: str, state: DebateExecState):
        """保存检查点"""
        config = {"configurable": {"thread_id": thread_id}}
        await self.saver.aput(config, state)

    async def restore(self, thread_id: str) -> DebateExecState | None:
        """恢复检查点"""
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint = await self.saver.aget(config)
        return checkpoint.values if checkpoint else None
```

#### 3.4.2 向量存储集成（案例库）

```python
# backend/app/services/case_library.py
from langchain_community.vectorstores import Milvus
from langchain_openai import OpenAIEmbeddings

class CaseLibrary:
    """历史案例库 - 语义检索"""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.vectorstore = Milvus(
            embedding_function=self.embeddings,
            collection_name="incident_cases",
            connection_args={"host": "localhost", "port": "19530"}
        )

    async def add_case(self, incident: Incident, report: Report):
        """添加历史案例"""
        doc = Document(
            page_content=f"{incident.description}\n{report.root_cause}",
            metadata={
                "incident_id": incident.id,
                "severity": incident.severity,
                "resolution_time": report.resolution_time
            }
        )
        await self.vectorstore.aadd_documents([doc])

    async def search_similar(self, query: str, k: int = 5) -> list[dict]:
        """语义检索相似案例"""
        results = await self.vectorstore.asimilarity_search(query, k=k)
        return [{"content": r.page_content, "metadata": r.metadata} for r in results]
```

---

## 四、改进优先级矩阵

| 改进项 | 影响度 | 工作量 | 优先级 | 参考框架 |
|--------|--------|--------|--------|----------|
| Agent定义统一 | 高 | 低 | P0 | OpenAI Agents |
| 并行执行 | 高 | 中 | P0 | AutoGen |
| ReAct工具集成 | 高 | 中 | P0 | LangChain |
| 动态图构建 | 中 | 高 | P1 | CrewAI |
| MCP工具集成 | 中 | 中 | P1 | OpenAI Agents |
| 持久化Checkpointer | 中 | 低 | P1 | LangGraph |
| Langfuse集成 | 中 | 低 | P2 | Langfuse |
| 案例向量库 | 低 | 高 | P2 | Dify RAG |

---

## 五、架构演进路线图

```
当前状态                      Phase 1                    Phase 2                    Phase 3
┌─────────────┐           ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
│ 串行执行    │    ──>    │ 并行执行    │    ──>    │ MCP工具集   │    ──>    │ 可观测性    │
│ 硬编码图    │           │ 动态图构建  │           │ ReAct循环   │           │ 案例库      │
│ 无持久化    │           │ Agent统一   │           │ 沙箱执行    │           │ Checkpoint  │
└─────────────┘           └─────────────┘           └─────────────┘           └─────────────┘
```

---

## 六、具体代码改动清单

### 6.1 需要修改的文件

| 文件 | 改动类型 | 改动内容 |
|------|----------|----------|
| `backend/app/runtime/langgraph/state.py` | 重构 | 统一AgentDefinition，简化state定义 |
| `backend/app/runtime/langgraph_runtime.py` | 重构 | 拆分为多个模块，支持并行执行 |
| `backend/app/runtime/langgraph/builder.py` | 增强 | 动态图构建，支持配置驱动 |
| `backend/app/services/agent_tool_context_service.py` | 增强 | MCP工具集成 |
| `backend/app/config.py` | 扩展 | 新增配置项（MCP、Langfuse、向量库等）|

### 6.2 需要新增的文件

| 文件 | 用途 |
|------|------|
| `backend/app/runtime/langgraph/parallel_executor.py` | 并行执行器 |
| `backend/app/runtime/langgraph/react_executor.py` | ReAct工具执行 |
| `backend/app/tools/mcp_toolkit.py` | MCP工具包 |
| `backend/app/observability/langfuse_integration.py` | 可观测性集成 |
| `backend/app/runtime/checkpointer.py` | 检查点持久化 |
| `backend/app/services/case_library.py` | 案例向量库 |
| `backend/app/runtime/tracing.py` | 内置追踪 |

---

## 七、测试策略

### 7.1 单元测试
- AgentDefinition序列化/反序列化
- 并行执行器的正确性和性能
- 动态图构建的各种配置场景

### 7.2 集成测试
- MCP工具调用端到端
- Checkpoint保存/恢复流程
- Langfuse追踪完整性

### 7.3 性能测试
- 并行vs串行执行时间对比
- 大规模工具调用内存占用
- 向量检索延迟

---

## 八、参考资料

- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) - Agent设计参考
- [AutoGen](https://github.com/microsoft/autogen) - 多Agent协作模式
- [LangGraph](https://github.com/langchain-ai/langgraph) - 图编排和持久化
- [Dify](https://github.com/langgenius/dify) - 工作流设计参考
- [CrewAI](https://github.com/crewAIInc/crewAI) - Flow设计模式
- [Langfuse](https://github.com/langfuse/langfuse) - 可观测性方案
- [MCP Servers](https://github.com/modelcontextprotocol/servers) - 工具生态
- [E2B Code Interpreter](https://github.com/e2b-dev/code-interpreter) - 沙箱执行