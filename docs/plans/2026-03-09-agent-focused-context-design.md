# 2026-03-09 Agent Focused Context Design

## 背景

当前多 Agent 运行时存在一个共同问题：

1. round 级上下文在进入各 Agent 之前被过度裁剪；
2. 工具返回结果只作为 `tool_context.data` 的压缩摘要注入 Prompt；
3. 各专家 Agent 拿到的是“线索碎片”，不是“围绕当前故障问题的证据闭包”；
4. `CodeAgent` 问题最明显，但同样的问题也存在于 `LogAgent`、`DomainAgent`、`DatabaseAgent`、`MetricsAgent`、`ChangeAgent`、`RunbookAgent`。

这会直接导致：
- Agent 只能做关键词复述，不能围绕问题入口做精准分析；
- 专家之间共享的是弱摘要，难以形成高质量交叉验证；
- LLM token 并不一定不足，但真正有价值的上下文没被送进去。

## 目标

在不推翻现有 LangGraph 编排结构的前提下，把各 Agent 的输入升级为：

- `base_context`：较完整的轮次基础上下文；
- `focused_context`：Agent 专属的“问题闭包证据包”；
- `tool_context`：工具调用审计与原始结果摘要。

核心目标：

1. 每个 Agent 面向自己最需要的证据，而不是共享同一份轻量摘要；
2. 先保留现有工作流、事件、审计、前端协议，降低回归风险；
3. 允许后续把 `focused_context` 继续升级为更强的代码调用链 / 日志时间线 / 数据库因果链分析入口。

## 方案对比

### 方案 A：仅放大 token 和截断阈值

做法：提高 `max_tokens`、放宽 `compact_context` 长度限制。

优点：改动最小。

缺点：
- 仍然是“把更多碎片塞给模型”；
- 无法形成 Agent 专属的因果闭包；
- Prompt 噪音会同步扩大。

### 方案 B：引入 Agent Focused Context 层

做法：
- 保留现有 `compact_context` 作为基础；
- 在运行时为每个 Agent 构造 `focused_context`；
- Prompt 显式注入 `focused_context` 区块；
- 工具上下文不再只做审计，也参与问题闭包构造。

优点：
- 结构清晰；
- 风险可控；
- 对现有前后端协议兼容性最好。

缺点：
- 需要改造后端运行时与工具上下文服务；
- 需要补测试。

### 方案 C：彻底重写为全图谱推理上下文

做法：
- 新增调用图、日志事件图、数据库因果图，所有 Agent 直接消费图结构。

优点：上限最高。

缺点：
- 当前改造面过大；
- 会显著影响现有运行时与前端事件协议；
- 不适合作为这一轮增量优化。

## 结论

采用方案 B。

## 设计

### 1. 运行时上下文分层

每个 Agent 最终输入结构改为：

- `incident_summary`
- `parsed_data`
- `interface_mapping`
- `investigation_leads`
- `tool_context`
- `focused_context`

其中：

- `tool_context` 继续负责工具是否使用、审计记录、请求/响应摘要；
- `focused_context` 负责围绕当前问题生成“Agent 专属闭包”。

### 2. Focused Context 设计

#### CodeAgent
- 问题入口：method/path/service/interface
- 责任田代码锚点：code_artifacts
- 仓库命中文件与关键代码窗口
- 候选调用链文件集合
- 代码级可疑点摘要

#### LogAgent
- 关键时间线事件
- 关键异常锚点（时间、组件、级别、文本）
- traceId/service/endpoint 关联摘要
- 日志放大链路摘要

#### DomainAgent
- 特性/领域/聚合根/owner_team/owner
- 命中责任田行摘要
- 依赖服务、监控项、数据库表
- 映射置信度与缺口

#### DatabaseAgent
- 目标表列表
- 表结构摘要
- 索引摘要
- 慢 SQL / Top SQL 摘要
- session/wait 事件摘要

#### MetricsAgent
- 指标异常信号列表
- 指标时间关系摘要
- 远程 telemetry/APM/Grafana/Loki 可用性摘要
- 缺失监控点

#### ChangeAgent
- 变更窗口提交摘要
- 最近变更 Top-K
- 与问题接口/服务的关联提示

#### RunbookAgent
- 匹配案例/Runbook 条目
- 推荐步骤
- 前置条件 / 验证项 / 风险项

### 3. Prompt 改造

Prompt 中新增“Agent 专属分析上下文”区块：

- 先展示主 Agent 命令；
- 再展示 focused_context；
- 再展示 tool_context；
- 再展示最近交互摘要；
- 历史摘要条数适度上调。

### 4. 裁剪策略改造

- 轮次上下文不再极限裁剪到过小阈值；
- Session compaction 放宽长度与列表上限；
- commander 仍保留较轻摘要，专家 Agent 使用更完整上下文。

### 5. 输出与兼容性

- 前端协议不变；
- 工具审计事件不变；
- 仅增强 Agent 输入质量与日志可解释性。

## 验证

1. 单元测试：
- focused_context 生成结果正确；
- compaction 不再过度截断关键字段；
- CodeAgent / DatabaseAgent / RunbookAgent 等保留原有行为。

2. 运行验证：
- 后端测试通过；
- 前端构建通过；
- Prompt 中可看到 focused_context 区块。
