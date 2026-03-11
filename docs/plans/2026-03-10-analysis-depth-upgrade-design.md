# Analysis Depth Upgrade Design

## Background

当前项目已经具备以下基础：

- 基于 LangGraph 的多 Agent 编排骨架
- 主 Agent 命令分发机制
- 各专家 Agent 的 focused context
- 工具调用与审计链
- 前端对分析过程、工具上下文和结果的展示能力

但分析深度仍然存在明显上限，主要体现在：

1. `CodeAgent` 仍是轻量静态分析，尚未形成完整的代码拓扑闭包。
2. `LogAgent` 仍主要基于日志文本构建时间线，未与 trace/span、实例维度、指标时间点做统一时序对齐。
3. `DatabaseAgent` 仍是快照归纳，未上升到执行计划、锁等待图、SQL 模式聚类。
4. `DomainAgent` 偏责任田映射与归属判断，尚未做严格的领域约束推理。
5. Agent 间讨论仍偏“受控交换结论”，不是开放式长程辩论。
6. 默认 `max_rounds=1`，天然限制深度推理与交叉验证。

本次设计采用**方案 B：在保持现有 LangGraph 主体和现有功能契约不变的前提下，增强分析深度与多轮辩论能力，并同步补强前端展示。**

## Goals

1. 保持现有 API、WebSocket 事件名称、前端主流程和报告输出不发生破坏性变化。
2. 将多 Agent 分析从“单轮专家分发 + 结论交换”升级为“可配置轮次的主 Agent 驱动长程辩论”。
3. 将 `CodeAgent / LogAgent / DatabaseAgent / DomainAgent` 升级为更贴近生产问题定位的深度分析 Agent。
4. 前端同步展示更深的分析轨迹、证据闭包和多轮讨论关系。

## Non-Goals

1. 不替换现有 LangGraph 技术栈。
2. 不引入外部数据库作为新依赖。
3. 不重写前端信息架构，只补现有页面能力。
4. 不在本次设计中引入真正的分布式 trace 后端或真实 APM 平台依赖；仍以本地/模拟接入入口优先。

## Chosen Approach

### Why Not Only Do Point Enhancements

只增强单个 Agent 的解析能力并不能解决根因分析质量问题。生产故障定位真正缺的不是某一个 Agent 的 prompt，而是：

- 更强的证据闭包
- 更长的交叉验证链
- 更明确的主 Agent 追问能力
- 更清晰的前端因果展示

因此本次采用“深度分析能力增强 + 长程辩论机制升级 + 前端可视化补强”的组合方案。

### Why Keep Existing LangGraph Skeleton

当前项目已经有：

- `StateGraph`
- `MessagesState`
- `checkpointer`
- `agent_mailbox`
- `supervisor -> expert -> judge` 主流程

这些基础已经足以承载升级。直接推翻重写会带来过高回归风险，因此本次以“增强能力，不破坏契约”为原则。

## Target Architecture

### 1. Long-Running Debate Loop

当前：

- 主 Agent 首轮分发
- 并行专家执行
- 很快进入 Judge 或结束

升级后：

1. 主 Agent 生成初始任务
2. 专家 Agent 执行并返回中间证据
3. 主 Agent 根据证据缺口和冲突生成第二轮追问
4. 必要时插入 `CriticAgent / RebuttalAgent`
5. `JudgeAgent` 根据证据覆盖度、结论稳定度和轮次上限决定是否收敛

停止条件不再只有“固定轮次”，而是变成以下组合：

- 达到最大轮次
- 证据覆盖度达到阈值
- Top-K 根因稳定
- `JudgeAgent` 置信度达标
- 主 Agent 明确要求停止

### 2. CodeAgent Depth Upgrade

从当前的：

- 接口入口
- 文件命中
- 方法链摘要

升级为：

- AST 或符号级入口定位
- `controller -> service -> dao -> sql -> downstream rpc` 代码闭包
- 方法级调用图摘要
- SQL 语句与 repository / mapper 的绑定
- 下游 HTTP/RPC client 依赖闭包
- 事务边界、连接池配置、重试逻辑、线程池、异步边界的显式识别

输出形态新增：

- `call_graph_summary`
- `sql_binding_summary`
- `downstream_rpc_summary`
- `resource_risk_points`
- `transaction_boundary_summary`

### 3. LogAgent Timeline Upgrade

从当前的：

- 文本时间线
- causal_timeline

升级为：

- trace_id / span_id / instance / service / metric point 对齐后的统一时间线
- `first_error -> local_amplifier -> cross-service propagation -> user_visible_failure`
- 关键节点与指标拐点绑定

输出形态新增：

- `trace_timeline`
- `instance_scope`
- `aligned_metric_markers`
- `propagation_chain`

### 4. DatabaseAgent Depth Upgrade

从当前的：

- 目标表
- 慢 SQL
- session 状态
- 锁/压力归纳

升级为：

- 执行计划摘要
- 锁等待图
- blocker/waiter chain
- SQL 模式聚类
- top sql 模式化归纳
- 数据库根因 vs 上游拖垮的显式区分

输出形态新增：

- `execution_plan_summary`
- `lock_wait_graph`
- `blocking_chain`
- `sql_pattern_clusters`
- `db_root_cause_assessment`

### 5. DomainAgent Constraint Upgrade

从当前的：

- 责任田归属
- 聚合根边界

升级为：

- 聚合根不变量
- 事务边界与领域操作顺序约束
- 领域服务依赖是否合法
- 关键领域动作与数据库写入/远程调用顺序检查

输出形态新增：

- `aggregate_invariants`
- `domain_constraint_checks`
- `transaction_order_constraints`
- `domain_violation_hypotheses`

### 6. Main Agent Upgrade

主 Agent 从“初始派单器”升级为“长程讨论主持人”：

- 初始拆解
- 基于专家结果二次追问
- 识别冲突证据并触发 Critic/Rebuttal
- 动态决定下一轮关注点
- 决定何时收敛

新增内部能力：

- evidence coverage tracking
- unresolved gap tracking
- top-k hypothesis tracking
- convergence scoring

### 7. Frontend Upgrade

前端同步补强，不改变主页面入口与基本结构，但增强内容层次：

1. 辩论过程页
- 支持多轮展开
- 支持“主 Agent 追问 -> 专家回答 -> 反证/反驳”关系显示
- 支持证据引用卡片

2. 事件明细
- 展示 trace/log/db/code 四类证据面板
- 展示每轮的关键变化点

3. 结果页
- Top-K 根因排序
- 证据覆盖图
- 因果链图
- 验证计划
- 反证/不确定性说明

## Data Flow Changes

### Runtime

新增运行时状态字段：

- `top_k_hypotheses`
- `evidence_coverage`
- `round_objectives`
- `round_gap_summary`
- `debate_stability_score`

### Agent Context

每个 Agent 的 `focused_context` 会继续保留，但增加更深层的结构化字段，而不是简单加长文本。

### Event Stream

新增事件类型建议：

- `agent_followup_command_issued`
- `debate_round_gap_updated`
- `top_k_hypotheses_updated`
- `evidence_coverage_updated`
- `agent_deep_context_prepared`

这些事件应保持向后兼容，不影响现有前端消费逻辑。

## Testing Strategy

### Unit Tests

1. `CodeAgent`
- 入口定位
- 调用闭包
- SQL/RPC 绑定

2. `LogAgent`
- trace 时间对齐
- propagation chain

3. `DatabaseAgent`
- lock wait graph
- SQL 模式聚类

4. `DomainAgent`
- 领域约束检查

5. Runtime
- 多轮追问
- 证据覆盖度收敛
- Top-K 根因稳定停止

### Integration Tests

- 单轮 quick 模式仍兼容
- 多轮 standard/deep 模式可正常收敛
- WebSocket 事件流不中断

### Frontend Verification

- 长程辩论过程正确展示
- 多轮追问和反证链可见
- Top-K 和证据覆盖图正常展示

## Risks

1. 运行时耗时上升
- 通过可配置轮次、可配置深度模式、可提前停止来控制

2. LLM token 使用上升
- 通过结构化 focused context 替代简单长文本堆叠

3. 事件流复杂度上升
- 通过新增事件、保留旧事件、前端渐进消费控制风险

4. CodeAgent 深度升级实现复杂
- 先做轻量 AST/符号级分析，不强依赖完整语言服务器

## Acceptance Criteria

1. `CodeAgent` 能输出代码闭包，而不是只有文件命中与方法摘要。
2. `LogAgent` 能把日志与 trace/span/实例/指标点做统一时间线对齐。
3. `DatabaseAgent` 能输出锁等待图和 SQL 模式聚类摘要。
4. `DomainAgent` 能输出领域约束检查结果，而不只是责任田归属。
5. 主 Agent 支持多轮追问和收敛，不再局限于单轮分发。
6. 前端能清晰展示多轮讨论、证据链、Top-K 根因和因果图。
7. quick 模式保持兼容，现有接口契约不破坏。
