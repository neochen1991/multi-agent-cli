# 生产问题根因分析系统 - LangGraph 多 Agent 改进计划

## 一、改进概览

| 类别 | P0 严重 | P1 中等 | P2 建议 | 合计 |
|------|---------|---------|---------|------|
| 架构问题 | 2 | 2 | 2 | 6 |
| 代码质量 | 1 | 2 | 1 | 4 |
| 性能优化 | 0 | 1 | 0 | 1 |
| **合计** | **3** | **5** | **3** | **11** |

---

## 二、P0 严重问题（需立即解决）

### 2.1 统一 Agent 定义系统

**现状问题**：
- `AgentSpec` (specs.py) 和 `AgentConfig` (agents/config.py) 两套重复定义
- 字段不一致：`AgentSpec` 4 字段 vs `AgentConfig` 9 字段
- 主流程使用 `AgentSpec`，工厂使用 `AgentConfig`

**改进方案**：
```
方案 A：合并为单一 AgentConfig（推荐）
- AgentSpec 作为 AgentConfig 的简化视图
- 或直接移除 AgentSpec，统一使用 AgentConfig

方案 B：保留分离但明确职责
- AgentSpec: 运行时最小规格（只读）
- AgentConfig: 完整配置定义（可修改）
```

**涉及文件**：
- `backend/app/runtime/langgraph/specs.py`
- `backend/app/runtime/agents/config.py`
- `backend/app/runtime/langgraph_runtime.py`
- `backend/app/runtime/agents/factory.py`

**预期效果**：
- 消除代码重复
- 降低维护成本
- 配置一致性保证

---

### 2.2 决定是否使用 ReAct Agent 与工具

**现状问题**：
- `AgentFactory` 创建带工具的 ReAct Agent
- 实际执行时绕过工厂，直接调用 LLM
- Agent 配置中定义的工具从未被调用

**改进方案**：
```
方案 A：完整实现 ReAct 模式（推荐）
- 重构 execution.py，使用 AgentFactory 创建的 Agent
- 集成工具调用（git_tool, read_file, search_in_files 等）
- Agent 可真正执行代码搜索、日志分析等操作

方案 B：移除工具系统
- 删除 AgentFactory 中的工具相关代码
- 删除 AgentConfig 中的 tools 字段
- 简化为纯 LLM 调用模式
```

**涉及文件**：
- `backend/app/runtime/langgraph/execution.py`
- `backend/app/runtime/agents/factory.py`
- `backend/app/tools/` 目录

**预期效果**：
- 方案 A：Agent 具备真实工具能力，分析更准确
- 方案 B：代码简化，减少理解成本

---

### 2.3 移除未使用的代码或补充实现

**现状问题**：
- `AgentFactory.create_all_agents()` 方法存在但未被调用
- `SupervisorRouter` 类定义完整但主流程使用另一套路由

**改进方案**：
- 确定使用路径后，移除冗余代码
- 或补充实现使其发挥作用

---

## 三、P1 中等问题（应尽快解决）

### 3.1 实现真正的并行分析

**现状问题**：
```python
# 当前实现（顺序执行）
async def _graph_analysis_parallel(self, state):
    for agent_name in self.PARALLEL_ANALYSIS_AGENTS:
        await execute_single_phase_agent(...)  # 顺序
```

**改进方案**：
```python
# 改进后（并行执行）
async def _graph_analysis_parallel(self, state):
    tasks = [
        execute_single_phase_agent(orchestrator, agent_name=name, ...)
        for name in self.PARALLEL_ANALYSIS_AGENTS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 处理结果...
```

**涉及文件**：
- `backend/app/runtime/langgraph_runtime.py`

**预期效果**：
- 性能提升约 3x（三个 Agent 并行）
- 总分析时间减少

---

### 3.2 统一 Supervisor 路由逻辑

**现状问题**：
| 组件 | 位置 | 用途 |
|------|------|------|
| SupervisorRouter | router/supervisor.py | 完整决策逻辑 |
| routing.py 函数 | langgraph/routing.py | 守卫和回退逻辑 |
| execute_supervisor_decide | nodes/supervisor.py | 执行入口 |
| _run_problem_analysis_supervisor_router | langgraph_runtime.py | LLM 动态路由 |

**改进方案**：
```
推荐架构：
┌─────────────────────────────────────┐
│         SupervisorOrchestrator       │
│  ┌─────────────┐  ┌───────────────┐  │
│  │ RuleBased   │  │ LLMBased      │  │
│  │ Router      │  │ Router        │  │
│  │ (Supervisor │  │ (Commander)   │  │
│  │  Router)    │  │               │  │
│  └─────────────┘  └───────────────┘  │
│         │                │             │
│         └────────┬───────┘             │
│                  ▼                     │
│         ┌───────────────┐              │
│         │ RouteGuardrail │             │
│         └───────────────┘              │
└─────────────────────────────────────┘
```

**涉及文件**：
- `backend/app/runtime/router/supervisor.py`
- `backend/app/runtime/langgraph/routing.py`
- `backend/app/runtime/langgraph/nodes/supervisor.py`

---

### 3.3 动态图构建

**现状问题**：
```python
# 当前实现（硬编码）
graph.add_node("log_agent_node", build_agent_node(self, "LogAgent"))
graph.add_node("domain_agent_node", build_agent_node(self, "DomainAgent"))
graph.add_node("code_agent_node", build_agent_node(self, "CodeAgent"))
# ... 每个 Agent 都要手动添加
```

**改进方案**：
```python
# 改进后（动态构建）
def build_graph(self, agent_configs: List[AgentConfig]):
    graph = StateGraph(DebateExecState)

    # 核心节点
    graph.add_node("init_session", build_init_session_node(self))
    graph.add_node("supervisor_decide", build_supervisor_node(self))

    # 动态添加 Agent 节点
    for config in agent_configs:
        node_name = f"{config.name.lower()}_node"
        graph.add_node(node_name, build_agent_node(self, config.name))

    # 动态构建路由表
    route_table = self._build_route_table(agent_configs)
    graph.add_conditional_edges("supervisor_decide", self._route, route_table)

    return graph.compile()
```

**涉及文件**：
- `backend/app/runtime/langgraph_runtime.py`

**预期效果**：
- 支持配置化添加/删除 Agent
- 更灵活的 Agent 编排

---

### 3.4 简化状态结构

**现状问题**：
```python
class DebateExecState(DebateMessagesState):
    messages: ...           # 继承的消息
    history_cards: ...      # Agent 证据卡片
    evidence_chain: ...     # 证据链（重复？）
    claims: ...             # 声明列表
    agent_outputs: ...      # Agent 输出字典
    context: ...            # 上下文
    context_summary: ...    # 上下文摘要
    # ... 共 17 个字段
```

**改进方案**：
```python
class DebateExecState(DebateMessagesState):
    # 核心状态
    context: Annotated[Context, merge_context]

    # Agent 执行记录（统一存储）
    agent_history: Annotated[List[AgentRecord], extend_history]

    # 控制流状态
    control: Annotated[ControlState, merge_control]

    # 输出
    output: Annotated[OutputState, take_latest]

# 拆分为子状态，更清晰
class Context(TypedDict):
    raw: Dict[str, Any]      # 原始上下文
    summary: Dict[str, Any]  # 摘要

class AgentRecord(TypedDict):
    agent_name: str
    phase: str
    output: Dict[str, Any]
    evidence: List[str]
    confidence: float
    timestamp: datetime

class ControlState(TypedDict):
    current_round: int
    next_step: str
    should_stop: bool
```

---

### 3.5 增加单元测试覆盖

**现状问题**：
- `backend/tests/` 目录下测试文件较少
- 核心路由逻辑缺少测试

**改进方案**：
```
backend/tests/
├── test_state_reducer.py      # 状态 Reducer 测试
├── test_router.py              # 路由逻辑测试
├── test_agent_factory.py       # Agent 工厂测试
├── test_supervisor.py          # Supervisor 测试
├── test_langgraph_runtime.py   # 运行时测试
└── test_integration.py         # 集成测试
```

---

## 四、P2 建议改进（可延后）

### 4.1 引入 Subgraph 分层架构

**改进方案**：
```python
from langgraph.graph import StateGraph

# 分析团队子图
def build_analysis_subgraph():
    subgraph = StateGraph(AnalysisState)
    subgraph.add_node("log_agent", log_agent_node)
    subgraph.add_node("code_agent", code_agent_node)
    subgraph.add_node("domain_agent", domain_agent_node)
    # 可并行执行
    return subgraph.compile()

# 批判团队子图
def build_critique_subgraph():
    subgraph = StateGraph(CritiqueState)
    subgraph.add_node("critic", critic_node)
    subgraph.add_node("rebuttal", rebuttal_node)
    return subgraph.compile()

# 主图
main_graph = StateGraph(MainState)
main_graph.add_node("analysis_team", build_analysis_subgraph())
main_graph.add_node("critique_team", build_critique_subgraph())
main_graph.add_node("judge", judge_node)
```

**预期效果**：
- 更好的模块化
- 子图可独立测试
- 支持真正的团队并行

---

### 4.2 增加可观测性

**改进方案**：
```python
# 增加结构化日志和追踪
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("agent_execution")
async def execute_agent(spec: AgentSpec, state: State):
    span = trace.get_current_span()
    span.set_attribute("agent.name", spec.name)
    span.set_attribute("agent.phase", spec.phase)
    # ...
```

---

### 4.3 支持断点续传

**现状问题**：
- 使用 `MemorySaver` 作为 checkpointer
- 进程重启后状态丢失

**改进方案**：
```python
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver

# 支持配置化的持久化
def get_checkpointer():
    if settings.CHECKPOINT_BACKEND == "postgres":
        return PostgresSaver(settings.DATABASE_URL)
    elif settings.CHECKPOINT_BACKEND == "sqlite":
        return SqliteSaver("checkpoints.db")
    else:
        return MemorySaver()
```

---

## 五、实施路线图

```
Phase 1: 基础架构修复（Week 1-2）
├── [P0] 统一 Agent 定义系统
├── [P0] 决定 ReAct Agent 方案
└── [P1] 增加核心单元测试

Phase 2: 核心功能优化（Week 3-4）
├── [P1] 实现并行分析
├── [P1] 统一 Supervisor 路由
└── [P1] 动态图构建

Phase 3: 架构升级（Week 5-6）
├── [P1] 简化状态结构
├── [P2] 引入 Subgraph 模式
└── [P2] 增加可观测性

Phase 4: 生产就绪（Week 7-8）
├── [P2] 支持断点续传
├── 完善测试覆盖
└── 性能优化和压测
```

---

## 六、改进清单检查表

### P0 严重问题

- [ ] **统一 Agent 定义**
  - [ ] 分析 AgentSpec 和 AgentConfig 的使用场景
  - [ ] 决定合并或分离策略
  - [ ] 实现统一方案
  - [ ] 更新所有引用
  - [ ] 添加测试

- [ ] **ReAct Agent 决策**
  - [ ] 评估工具调用的必要性
  - [ ] 选择方案 A（实现）或方案 B（移除）
  - [ ] 执行选定方案
  - [ ] 更新文档

- [ ] **清理未使用代码**
  - [ ] 移除或实现 AgentFactory 未使用方法
  - [ ] 统一 SupervisorRouter 使用路径

### P1 中等问题

- [ ] **并行分析实现**
  - [ ] 重构 `_graph_analysis_parallel` 方法
  - [ ] 处理并行执行异常
  - [ ] 添加并行测试

- [ ] **统一 Supervisor 路由**
  - [ ] 设计统一路由架构
  - [ ] 重构路由逻辑
  - [ ] 迁移现有实现

- [ ] **动态图构建**
  - [ ] 设计动态节点注册机制
  - [ ] 重构图构建逻辑
  - [ ] 支持配置化 Agent

- [ ] **状态结构简化**
  - [ ] 设计新的状态结构
  - [ ] 迁移现有状态
  - [ ] 更新所有 reducer

- [ ] **测试覆盖**
  - [ ] 状态 reducer 测试
  - [ ] 路由逻辑测试
  - [ ] Agent 工厂测试

### P2 建议改进

- [ ] **Subgraph 架构**
  - [ ] 设计子图结构
  - [ ] 实现子图构建
  - [ ] 集成到主图

- [ ] **可观测性**
  - [ ] 添加 OpenTelemetry 支持
  - [ ] 结构化日志
  - [ ] 性能指标

- [ ] **断点续传**
  - [ ] 实现持久化 checkpointer
  - [ ] 状态恢复逻辑
  - [ ] 测试验证

---

## 七、风险与依赖

| 改进项 | 风险 | 依赖 |
|--------|------|------|
| 统一 Agent 定义 | 中 - 可能影响现有流程 | 无 |
| ReAct Agent 实现 | 高 - 需要工具集成 | 工具系统完善 |
| 并行分析 | 低 - asyncio 成熟 | 无 |
| Subgraph 架构 | 高 - 大规模重构 | 完整测试覆盖 |
| 状态结构简化 | 中 - 需要数据迁移 | 完整测试覆盖 |

---

## 八、验收标准

### 功能验收

- [ ] 所有 Agent 正常工作
- [ ] 路由决策正确
- [ ] 并行分析执行成功
- [ ] 测试覆盖率 > 80%

### 性能验收

- [ ] 并行分析时间 < 串行时间的 40%
- [ ] 单次完整分析 < 60s
- [ ] 内存使用稳定

### 代码质量

- [ ] 无重复代码
- [ ] 类型注解完整
- [ ] 文档更新