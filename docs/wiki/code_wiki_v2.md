# Code Wiki V2

本文档面向首次接手本项目的工程师，目标不是逐行解释源码，而是帮助读者快速建立三个认知：

1. 这个系统到底解决什么问题。
2. 一次生产问题分析请求是如何穿过前后端和多 Agent 运行时的。
3. 如果要扩展新 Agent、新工具、新数据源，应该从哪里下手。

本文基于当前代码状态编写，重点覆盖：
- 前端调查工作台与战情页。
- 后端服务层、Flow 层和 LangGraph 运行时。
- Tool / Skill / Connector 体系。
- Benchmark、治理和可靠性守护。

## 1. 项目定位

本项目是一个“生产问题根因分析系统”的代码示例。它不是通用问答机器人，也不是单一 Agent 的聊天应用，而是一套围绕生产故障调查流程构建的多 Agent 系统。

系统目标：
- 接收用户输入的故障描述、错误日志、堆栈、监控现象。
- 自动完成责任田资产映射。
- 由主 Agent 协调多个专家 Agent 分工分析。
- 在可审计的工具调用前提下收集证据。
- 输出可解释、可回放、可追责的根因结论与报告。

系统边界：
- 主 Agent 负责调度、命令分发、收敛和报告归纳。
- 专家 Agent 负责日志、代码、领域、数据库等维度的分析。
- 工具调用必须经过开关控制和命令门禁。
- 当前默认以本地文件、本地配置和内存 / markdown 持久化为主，真实平台接入能力通过 Connector 预留。

关键文档：
- `/Users/neochen/multi-agent-cli_v2/README.md`
- `/Users/neochen/multi-agent-cli_v2/AGENTS.md`

## 2. 建议的阅读顺序

如果你第一次看这个仓库，不要直接扎进 `langgraph_runtime.py`。建议按下面顺序读：

1. `/Users/neochen/multi-agent-cli_v2/backend/app/main.py`
2. `/Users/neochen/multi-agent-cli_v2/backend/app/api/router.py`
3. `/Users/neochen/multi-agent-cli_v2/backend/app/api/debates.py`
4. `/Users/neochen/multi-agent-cli_v2/backend/app/api/ws_debates.py`
5. `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
6. `/Users/neochen/multi-agent-cli_v2/backend/app/flows/debate_flow.py`
7. `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
8. `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/`
9. `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
10. `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/WarRoom/index.tsx`

这样读的原因很简单：
- 先搞清楚入口。
- 再搞清楚主流程。
- 最后再进入运行时细节。

## 3. 系统总体结构

从工程实现看，系统分成四层：

1. 前端工作台层
   - 负责输入故障信息、展示资产映射、流式对话、工具调用、结论和报告。

2. API / Service / Flow 层
   - 负责接收请求、创建会话、持久化中间态、驱动业务流程。

3. LangGraph 多 Agent 运行时层
   - 负责图编排、状态管理、Agent 节点执行、路由、超时重试和事件分发。

4. Tool / Skill / Connector / Governance 层
   - 负责工具能力、方法论注入、外部系统适配、评测和治理。

后端主目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/api`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services`
- `/Users/neochen/multi-agent-cli_v2/backend/app/flows`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph`
- `/Users/neochen/multi-agent-cli_v2/backend/app/tools`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/connectors`
- `/Users/neochen/multi-agent-cli_v2/backend/app/benchmark`
- `/Users/neochen/multi-agent-cli_v2/backend/app/governance`

前端主目录：
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages`

## 4. 后端分层说明

### 4.1 API 层

API 层负责暴露 HTTP 和 WebSocket 入口，不承载复杂业务逻辑。

核心文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/main.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/router.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/debates.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/ws_debates.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/assets.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/settings.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/reports.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/benchmark.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/governance.py`

职责：
- 创建 incident / session。
- 启动同步、异步、后台分析。
- 提供会话详情、结果、报告、取消和重试入口。
- 建立 `/ws/debates/{session_id}` 实时事件流连接。

### 4.2 Service 层

Service 层承载真正的业务能力，不是简单 CRUD。

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/asset_service.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/report_service.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/report_generation_service.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_skill_service.py`

职责：
- 组织分析请求的业务上下文。
- 调用责任田资产映射。
- 驱动多 Agent runtime 执行。
- 汇总结果并生成报告。
- 给 Agent 注入工具和 Skill 上下文。

### 4.3 Flow 层

Flow 层比 Service 更接近“用户旅程”。它会把多个服务和 runtime 串起来，形成一次完整调查。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/flows`

可以把它理解成：
- Service 更像领域能力。
- Flow 更像业务编排。

### 4.4 Repository / Model 层

当前项目暂不依赖外部数据库作为主存储，而是以本地文件、markdown、json 和内存对象保存会话、报告和资产数据。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/models`
- `/Users/neochen/multi-agent-cli_v2/backend/app/repositories`

### 4.5 Core / Governance / Benchmark 层

这几层是“系统能力底座”：

- `core`
  - 配置、日志、异常、基础设施定义。
- `governance`
  - 治理、风险动作、系统卡、审批和约束。
- `benchmark`
  - 标准故障样本、批量评测、评分逻辑、CI Gate 能力。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/core`
- `/Users/neochen/multi-agent-cli_v2/backend/app/governance`
- `/Users/neochen/multi-agent-cli_v2/backend/app/benchmark`

## 5. 前端分层说明

前端不是一个简单表单页，而是一套“调查工作台”。

当前页面目录：
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Home/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/WarRoom/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/InvestigationWorkbench/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/History/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Settings/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/ToolsCenter/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/BenchmarkCenter/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Assets/index.tsx`

页面职责：
- `Home`
  - 概览、能力介绍、入口导航。
- `Incident`
  - 用户输入故障信息并实时查看分析过程。
- `WarRoom`
  - 聚合战情视角，强调时间线、证据链和关键结论。
- `InvestigationWorkbench`
  - 以调查会话为中心组织过程回放。
- `History`
  - 查看历史会话和结果。
- `Assets`
  - 维护并展示责任田资产。
- `Settings` / `ToolsCenter` / `BenchmarkCenter` / `GovernanceCenter`
  - 配置、工具中心、评测中心和治理中心。

## 6. 一次分析请求的端到端流程

下面按真实业务顺序描述一次会话。

### 6.1 用户提交故障信息

用户在 `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx` 输入：
- 故障现象
- 报错日志
- 堆栈
- 监控现象
- 可选的责任田上下文或接口信息

前端调用 debate API 创建 incident 和 session，并建立 WebSocket 连接。

### 6.2 后端创建会话

API 入口位于：
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/debates.py`

相关逻辑会：
- 创建分析会话。
- 保存初始上下文。
- 触发同步或异步执行。

### 6.3 资产映射先行

Service 层会先做责任田映射，包括：
- 接口归属
- 领域 / 聚合根
- 代码清单
- 数据库表
- 依赖服务
- 监控清单

这是因为后面的专家 Agent 不应该在完全盲目的上下文下工作。

### 6.4 主 Agent 初判并下发命令

运行时进入主 Agent / Supervisor 节点，完成：
- 问题初步归因方向判断。
- 选择需要参与的专家 Agent。
- 下发命令。
- 指定每个 Agent 应该聚焦的证据点。

这是系统的硬约束之一：先有命令，后有专家执行。

### 6.5 专家 Agent 执行分析与工具调用

各专家 Agent 在命令门禁下进行：
- 读取责任田映射结果。
- 按需使用工具。
- 输出结构化结论、证据和不确定项。

如果工具开关关闭，Agent 会退化为只使用已有上下文分析。

### 6.6 裁决与报告生成

主 Agent 和 JudgeAgent 会对多方结论进行收敛：
- 生成 Top-K 根因候选。
- 组织证据链。
- 形成主结论。
- 生成报告、修复建议和验证建议。

### 6.7 前端流式展示

前端通过 WebSocket 实时接收：
- 阶段事件
- Agent 发言
- 工具调用记录
- 资产映射结果
- 裁决和报告结果

最终在不同标签页展示：
- 资产映射
- 辩论过程
- 辩论结果
- 报告结果

## 7. API 与 WebSocket 入口

### 7.1 应用启动

应用启动入口：
- `/Users/neochen/multi-agent-cli_v2/backend/app/main.py`

关键点：
- `create_application()` 负责组装 FastAPI 应用。
- `main.py` 会挂载 REST router 和 WebSocket router。

### 7.2 REST Router

聚合入口：
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/router.py`

这里通过 `include_router` 把多个业务 API 聚合起来，包括：
- debates
- incidents
- assets
- settings
- reports
- benchmark
- governance

### 7.3 WebSocket Router

实时分析的关键入口：
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/ws_debates.py`

它负责：
- 接受客户端连接。
- 校验 token。
- 发送会话快照。
- 推送事件流。
- 在需要时触发自动启动分析。

设计原因：
- 根因分析是长流程任务。
- 只靠轮询会让前端体验很差，也不利于展示中间过程。

## 8. DebateService 是业务主入口

核心类：
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`

从代码入口看，`DebateService` 是业务层主编排器。它的职责不是取代 runtime，而是把业务上下文整理好，再交给 runtime。

它负责：
- 读取会话和 incident 信息。
- 构建 runtime 输入上下文。
- 执行资产映射。
- 调用 LangGraph 运行时。
- 处理执行异常和终态收敛。
- 持久化过程结果和最终结果。

你可以把它看成：
- 上半部分处理业务。
- 下半部分把任务转交给多 Agent runtime。

## 9. LangGraph 运行时核心

当前运行时核心目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph`

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/builder.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/agent_runner.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/event_dispatcher.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/execution.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/phase_executor.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/phase_manager.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/checkpointer.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/doom_loop_guard.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/session_compaction.py`

### 9.1 Orchestrator

主入口类：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`

当前 orchestrator 负责协调多个运行时模块：
- 图构建
- 状态初始化
- 节点执行
- 事件分发
- 终态收敛

### 9.2 GraphBuilder

图定义入口：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/builder.py`

它负责把节点和边定义成 LangGraph 可执行图。这里决定：
- 有哪些节点。
- 节点之间如何跳转。
- 哪些条件会收敛到 judge 或结束节点。

### 9.3 State

状态定义文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state.py`

状态承载的不是单一文本，而是一组结构化信息：
- 对话消息
- 当前阶段
- 路由决策
- Agent 输出
- 工具结果
- 证据链
- 最终结论

### 9.4 Node 与执行链

节点目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes`

主要包括：
- `supervisor.py`
- `agents.py`
- `agent_subgraph.py`
- `core.py`

这些节点的职责是：
- 主 Agent / Supervisor 做调度。
- 各专家 Agent 做分析和工具调用。
- Judge 或聚合节点收敛输出。

### 9.5 可靠性组件

相关文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/checkpointer.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/doom_loop_guard.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/session_compaction.py`

这些模块的意义：
- `checkpointer`
  - 保存运行态，支持恢复。
- `doom_loop_guard`
  - 防止 Agent 进入循环提问或重复执行。
- `session_compaction`
  - 控制历史上下文体积，避免消息不断膨胀。

## 10. 多 Agent 角色说明

当前系统的 Agent 不是“大家一起自由说话”，而是“主 Agent 指挥，专家 Agent 分工执行，Judge 收敛”。

关键配置与定义：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/specs.py`
- `/Users/neochen/multi-agent-cli_v2/docs/agents/agent-catalog.md`
- `/Users/neochen/multi-agent-cli_v2/docs/agents/protocol-contracts.md`

主要角色：

### 10.1 ProblemAnalysisAgent / MainAgent

职责：
- 接收会话全局上下文。
- 做初步问题拆解。
- 给其他 Agent 下命令。
- 收集阶段性结果。
- 输出主结论或提交给 Judge。

### 10.2 LogAgent

职责：
- 分析日志、异常链路、错误码、时序和重试行为。
- 从网关、服务、基础设施日志中找因果证据。

可用输入：
- 用户输入日志。
- 本地日志文件或未来的日志平台 connector。

### 10.3 CodeAgent

职责：
- 查找代码入口、调用链、事务边界、重试逻辑、资源释放问题。
- 分析是否存在已知实现缺陷。

可用输入：
- 本地仓库代码。
- 远程 Git 仓库 clone / grep 结果。

### 10.4 DomainAgent

职责：
- 解析责任田资产。
- 判断接口归属、领域、聚合根、依赖服务和变更影响面。

### 10.5 DatabaseAgent

职责：
- 读取数据库表、字段、索引、锁、慢 SQL、session 状态等信息。
- 将业务问题与数据库对象关联起来。

### 10.6 CriticAgent

职责：
- 对已有结论提出反证和质疑。
- 强制暴露证据不足或逻辑跳跃。

### 10.7 JudgeAgent

职责：
- 收敛多方证据。
- 生成 Top-K 根因候选。
- 评估置信度和最终建议。

## 11. Prompt、上下文构建与解析

影响 Agent 质量的不是只有模型本身，更关键的是三件事：
- 给什么上下文。
- 怎么组织 prompt。
- 怎么解析结果。

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompt_builder.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/context_builders.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/parsers.py`

### 11.1 Prompt 分层

当前实现不是把所有内容塞进一个 prompt，而是分层组织：
- system prompt
- agent role prompt
- 主 Agent 命令 prompt
- 上下文摘要
- 工具结果摘要

### 11.2 Context Builder

作用：
- 裁剪 incident 原始输入。
- 注入责任田映射结果。
- 选择历史消息摘要。
- 注入工具调用结果。

### 11.3 Parser

作用：
- 把 LLM 自然语言输出转成结构化对象。
- 提取 `chat_message`、证据、结论、风险和待确认项。

这一步非常关键，因为前端展示和结果收敛不能依赖自由文本猜测。

## 12. Tool、Skill 与 Connector

这是当前项目和普通多 Agent Demo 差异最大的部分之一。

### 12.1 Tool

Tool 是运行时实际可执行的动作。

例如：
- 读取本地日志文件。
- 搜索本地或远程 Git 仓库代码。
- 查询 PostgreSQL 元数据。
- 解析责任田 Excel / markdown 资产。

相关目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/tools`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/tool_registry`

### 12.2 Skill

Skill 不是代码执行器，而是“方法论注入层”。

相关服务：
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_skill_service.py`

作用：
- 给 Agent 注入特定分析套路。
- 控制哪些 Agent 命中哪些 Skill。
- 记录 Skill 命中审计信息。

### 12.3 Connector

Connector 是对外部系统的适配层。

相关目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/connectors`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime_ext/integrations`

当前设计方向：
- 即使真实平台暂未启用，也要先有接入入口和开关。
- 在没有真实平台时，允许本地文件模拟。

### 12.4 Tool Context Service

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`

作用：
- 根据当前 Agent、当前命令和配置开关决定可用工具。
- 给 Agent 注入可调用能力和工具上下文。
- 控制命令门禁和审计信息。

## 13. 事件模型与前端流式展示

实时分析体验的核心不在“最终报告”，而在“过程可见”。

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/ws_debates.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/core/event_schema.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/event_dispatcher.py`
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`

从 `Incident/index.tsx` 可以看到，前端维护了多类状态：
- `debateResult`
- `reportResult`
- `debateMaxRounds`
- `eventRecords`
- `timelineItems`
- `dialogueMessages`

前端会按事件类型做不同映射：
- 资产映射事件
- 辩论进展事件
- 工具调用事件
- 结果事件
- 报告事件

为什么要这样设计：
- 用户需要区分“谁在说话”和“谁在调用工具”。
- 用户需要看到阶段变化，而不是只看最终结论。
- 资产映射结果应该先于辩论可见。

## 14. 责任田资产体系

本项目的一个核心特点，是把“责任田资产”作为根因分析的先验知识。

资产维度包括：
- 特性
- 领域
- 聚合根
- 前端页面
- API 接口
- 代码清单
- 数据库表
- 依赖服务
- 监控清单

相关页面：
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Assets/index.tsx`

相关 API：
- `/Users/neochen/multi-agent-cli_v2/backend/app/api/assets.py`

资产体系的意义：
- 让分析不从零开始。
- 让主 Agent 能把数据库表等信息传递给 DatabaseAgent。
- 为后续真实 CMDB / 拓扑 / ownership 接入打基础。

## 15. 数据库能力

本项目已经引入 DatabaseAgent，并针对 PostgreSQL 预留了能力入口。

设计目标：
- 根据责任田映射到的数据库表，进一步查询：
  - 表结构
  - 字段定义
  - 索引信息
  - 慢 SQL
  - Top SQL
  - session 状态
  - 锁等待

即使当前没有真实 PG 数据源，也要求：
- 配置入口存在。
- 开关存在。
- 无真实连接时能优雅降级。

## 16. 可靠性与治理机制

这是项目区别于“玩具 Agent”实现的重要部分。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/core`
- `/Users/neochen/multi-agent-cli_v2/backend/app/governance`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph`

关键能力：
- 超时控制
- 重试
- 降级
- 终态保证
- 断点续写
- 循环保护
- 审计
- 风险动作治理

必须满足的运行时约束，已沉淀在：
- `/Users/neochen/multi-agent-cli_v2/AGENTS.md`
- `/Users/neochen/multi-agent-cli_v2/docs/agents/reliability-governance.md`
- `/Users/neochen/multi-agent-cli_v2/docs/agents/checkpoint-resume.md`

## 17. Benchmark 与 CI Gate

当前项目不只强调“能跑通”，还强调“可量化评估”。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/benchmark`

目标：
- 用标准 incident 样本评估系统。
- 测量超时率、命中率、Top-K 质量、报告质量。
- 未来对接 CI Gate，阻断明显回归。

这是面向开源和持续演进非常必要的一层，因为多 Agent 系统很容易因为 prompt、路由或工具变更发生退化。

## 18. 当前前端页面重点

### 18.1 Incident 页面

关键文件：
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`

这是最重要的业务页之一，负责：
- 创建和恢复会话。
- 建立 WebSocket。
- 管理资产映射、辩论过程、结果和报告四类视图。
- 做事件去重、消息过滤、时间线生成、报告渲染。

### 18.2 WarRoom 页面

关键文件：
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/WarRoom/index.tsx`

定位：
- 提供更偏战情的大盘视图。
- 聚焦时间线、关键结论、工具调用和关键指标。

### 18.3 Assets 页面

关键文件：
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Assets/index.tsx`

定位：
- 提供资产导入、资产查询和资产展示入口。

## 19. 如何新增一个 Agent

推荐顺序不是直接改代码，而是先补协议和文档。

步骤：
1. 在文档中定义这个 Agent 的职责、输入、输出、工具权限和治理要求。
2. 更新 `/Users/neochen/multi-agent-cli_v2/docs/agents/agent-catalog.md`
3. 更新 `/Users/neochen/multi-agent-cli_v2/docs/agents/protocol-contracts.md`
4. 在 `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/specs.py` 注册 Agent。
5. 补 prompt、context builder、parser 和节点逻辑。
6. 通过 `agent_tool_context_service` 和 `agent_skill_service` 接入能力。
7. 在前端补齐展示。
8. 补 benchmark / smoke case。

关键原则：
- 先协议，后实现。
- 先命令门禁，后工具调用。
- 先结构化输出，后自然语言润色。

## 20. 如何新增 Tool / Skill / Connector

### 20.1 新增 Tool

适用于：
- 需要让 Agent 真正执行某个查询或读取动作。

要求：
- 明确输入输出协议。
- 明确哪些 Agent 可用。
- 明确命令门禁条件。
- 必须记录调用审计。

### 20.2 新增 Skill

适用于：
- 需要为 Agent 注入某类分析套路或方法论。

要求：
- 控制体积。
- 明确命中条件。
- 避免和核心 prompt 发生职责冲突。
- 必须记录命中审计。

### 20.3 新增 Connector

适用于：
- 需要接外部日志平台、代码平台、监控平台、APM、CMDB 等系统。

要求：
- 必须有开关。
- 无法访问时要优雅降级。
- 允许本地文件作为模拟数据源。

## 21. 本地运行与排障

建议重点查看：
- `/Users/neochen/multi-agent-cli_v2/scripts`
- `/Users/neochen/multi-agent-cli_v2/.run/logs`

排障顺序建议：

1. 先看服务是否启动。
2. 再看 API 是否能创建 session。
3. 再看 WebSocket 是否成功连接。
4. 再看资产映射是否先产出结果。
5. 再看主 Agent 是否发出命令。
6. 再看专家 Agent 是否执行。
7. 再看工具调用是否真正发生。
8. 最后看报告生成是否完成。

常见问题：
- 长时间 pending
- Agent TimeoutError
- WebSocket 有连接但无过程事件
- 责任田未命中
- 工具调用未触发
- 前端消息重复展示
- 报告未生成或只生成空结论

## 22. 当前实现的复杂点与后续重构方向

为了让开源读者理解现状，这里需要明确当前实现仍有演进空间。

主要复杂点：
- 运行时模块较多，理解成本高。
- runtime 和 service 之间还有继续收敛空间。
- prompt / parser / context 仍可以进一步组件化。
- Tool / Connector 的真实数据源接入还在扩展中。
- 前端战情页与调查工作台还可以继续统一视图心智。

建议的下一步重构方向：
- 继续压缩 orchestrator 复杂度。
- 让节点、状态、路由和执行链职责更清晰。
- 强化工具审计和证据引用链。
- 提升报告、证据链和 Top-K 根因的可视化质量。
- 完善 benchmark 与 CI Gate 的闭环。

## 23. 推荐的阅读方法

如果你是不同角色，建议这样读：

- 后端工程师
  - 从 `main.py -> api -> debate_service -> runtime/langgraph` 开始。

- 前端工程师
  - 从 `Incident -> WarRoom -> Assets -> API client` 开始。

- Agent / Prompt 工程师
  - 从 `specs.py -> prompts.py -> prompt_builder.py -> parsers.py` 开始。

- 平台 / SRE 工程师
  - 从 `assets / tools / connectors / benchmark / governance` 开始。

## 24. 文档维护建议

这份 wiki 不应该成为一次性文档，而应该成为开源后的长期维护入口。

建议配套拆分：
- `code-wiki-overview`
- `code-wiki-runtime`
- `code-wiki-frontend`
- `code-wiki-extension-guide`
- `code-wiki-debugging`

同时要求：
- 每次新增 Agent、协议、工具或路由策略，都同步更新文档。
- 每次改变主流程，都同步更新阅读入口和调用链。

这样，文档才能真正跟住代码，而不是停留在历史实现上。
