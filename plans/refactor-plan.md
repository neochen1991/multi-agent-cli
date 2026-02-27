# 生产问题根因分析系统 - LangGraph 多 Agent 架构改进计划

## 一、改进目标

将当前单体 Orchestrator 架构重构为符合 LangGraph 最佳实践的多 Agent 协作架构，提升可维护性、可扩展性和可测试性。

## 二、改进原则

1. **渐进式改进**：每次改动保持系统可运行
2. **单一职责**：每个模块只做一件事
3. **依赖注入**：便于测试和扩展
4. **保持兼容**：API 接口不变

## 三、改进阶段

### Phase 1: 基础重构 (优先级: 高)

#### 1.1 拆分 Orchestrator 职责
- **目标**: 将 2200+ 行的 Orchestrator 拆分为多个专注的组件
- **改动**:
  - [ ] 创建 `AgentExecutor` 类 - 负责 Agent 调用
  - [ ] 创建 `RoutingCoordinator` 类 - 负责路由决策
  - [ ] 创建 `GraphBuilder` 重构版 - 负责图构建
  - [ ] 创建 `StateContext` 类 - 负责状态管理
  - [ ] 精简 `LangGraphRuntimeOrchestrator` 为协调层

#### 1.2 优化状态管理
- **目标**: 精简状态字段，消除冗余
- **改动**:
  - [ ] 审计 `DebateExecState` 字段必要性
  - [ ] 移除可通过计算获取的冗余字段
  - [ ] 添加状态验证器

### Phase 2: 架构优化 (优先级: 中)

#### 2.1 引入 Subgraph 模式
- **目标**: 使用 LangGraph 子图组织阶段
- **改动**:
  - [ ] 创建 `AnalysisPhaseSubgraph` - 分析阶段子图
  - [ ] 创建 `CritiquePhaseSubgraph` - 批判阶段子图
  - [ ] 创建 `JudgmentPhaseSubgraph` - 裁决阶段子图
  - [ ] 主图通过子图节点组织

#### 2.2 路由策略完全解耦
- **目标**: 路由逻辑与图结构完全分离
- **改动**:
  - [ ] 完善 `RoutingStrategy` 接口
  - [ ] 实现纯函数路由决策
  - [ ] 支持策略热切换

### Phase 3: 能力增强 (优先级: 低)

#### 3.1 支持 Human-in-the-Loop
- **目标**: 关键决策点支持人工介入
- **改动**:
  - [ ] 实现 `interrupt_before` 机制
  - [ ] 添加人工审核节点
  - [ ] 支持恢复执行

#### 3.2 配置外部化
- **目标**: Agent 配置从代码移到配置文件
- **改动**:
  - [ ] 支持 YAML 配置加载
  - [ ] 支持运行时动态注册 Agent
  - [ ] 配置热重载

## 四、详细实施步骤

### Step 1: 创建核心组件接口

```
backend/app/runtime/
├── core/
│   ├── __init__.py
│   ├── executor.py        # AgentExecutor
│   ├── coordinator.py     # RoutingCoordinator
│   ├── context.py        # StateContext
│   └── interfaces.py      # 抽象接口
```

### Step 2: 重构 Agent 执行

1. 从 Orchestrator 提取 Agent 调用逻辑
2. 创建 `AgentExecutor` 类
3. 支持 ReAct 和 Tool 调用

### Step 3: 重构路由逻辑

1. 整合 `RoutingStrategy` 和 `SupervisorRouter`
2. 创建纯函数路由决策
3. 支持多种路由策略

### Step 4: 重构图构建

1. 扩展 `GraphBuilder` 支持子图
2. 实现阶段子图
3. 主图组装子图

### Step 5: 精简 Orchestrator

1. 移除已提取的逻辑
2. 保留协调职责
3. 更新测试

## 五、文件变更清单

### 新增文件
- `backend/app/runtime/core/__init__.py`
- `backend/app/runtime/core/interfaces.py`
- `backend/app/runtime/core/executor.py`
- `backend/app/runtime/core/coordinator.py`
- `backend/app/runtime/core/context.py`
- `backend/app/runtime/graphs/__init__.py`
- `backend/app/runtime/graphs/analysis_subgraph.py`
- `backend/app/runtime/graphs/critique_subgraph.py`
- `backend/app/runtime/graphs/judgment_subgraph.py`

### 修改文件
- `backend/app/runtime/langgraph_runtime.py` - 精简
- `backend/app/runtime/langgraph/state.py` - 优化状态
- `backend/app/runtime/langgraph/builder.py` - 扩展子图支持
- `backend/app/runtime/router/__init__.py` - 整合策略
- `backend/app/runtime/agents/config.py` - 支持外部配置

### 新增测试
- `backend/tests/test_executor.py`
- `backend/tests/test_coordinator.py`
- `backend/tests/test_subgraphs.py`

## 六、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 破坏现有功能 | 高 | 保持原有 API，增量重构 |
| 性能下降 | 中 | 基准测试，性能监控 |
| 状态不一致 | 高 | 状态验证器，单元测试 |

## 七、验收标准

1. [ ] `LangGraphRuntimeOrchestrator` 代码量 < 500 行
2. [ ] 所有现有测试通过
3. [ ] 新增组件测试覆盖率 > 80%
4. [ ] 支持子图模式运行
5. [ ] 路由策略可独立测试