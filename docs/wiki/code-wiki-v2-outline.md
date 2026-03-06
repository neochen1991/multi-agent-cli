# Code Wiki V2 大纲

本文档用于规划新版 code wiki 的章节结构，目标是让新读者能够沿着“业务目标 -> 主流程 -> 运行时 -> 扩展点 -> 调试排障”的路径快速理解本项目。

当前项目已经不再只是一个简单的多 Agent Demo，而是一个包含前端战情页、LangGraph 运行时、工具治理、Benchmark、治理与评测能力的生产问题根因分析系统。因此，新版 wiki 需要覆盖当前真实实现，而不是只解释早期的 LangGraph 编排代码。

## 1. 项目总览

这一章回答两个问题：
- 这个系统要解决什么问题。
- 为什么它是“生产问题根因分析系统”，而不是普通聊天型 Agent。

建议内容：
- 目标用户：SRE、值班工程师、研发、架构师。
- 核心价值：责任田映射、证据收集、Agent 协作分析、可回放、可审计。
- 系统边界：主 Agent 负责调度与收敛；专家 Agent 负责取证与分析；工具调用受开关和命令门禁控制。

关键入口：
- `/Users/neochen/multi-agent-cli_v2/README.md`
- `/Users/neochen/multi-agent-cli_v2/AGENTS.md`

## 2. 从哪里开始读代码

这一章给新同学一条最短阅读路径，避免一上来陷入大文件和复杂目录。

推荐阅读顺序：
1. `backend/app/main.py`
2. `backend/app/api/router.py`
3. `backend/app/services/debate_service.py`
4. `backend/app/flows/debate_flow.py`
5. `backend/app/runtime/langgraph_runtime.py`
6. `frontend/src/pages/Incident/index.tsx`
7. `frontend/src/pages/WarRoom/index.tsx`

需要解释：
- REST 和 WebSocket 如何进入系统。
- 分析请求如何进入 service，再进入 flow 和 runtime。
- 前端如何订阅实时事件并渲染调查过程。

## 3. 后端整体分层

这一章从工程结构角度解释后端，而不是逐个目录罗列。

建议分层：
- `api`：HTTP / WebSocket 入口。
- `services`：业务编排与聚合服务。
- `flows`：将多个 service 和 runtime 串成完整业务流。
- `runtime/langgraph`：多 Agent 图编排、节点执行、状态与路由。
- `runtime_ext`：额外运行时扩展能力。
- `tools`：工具定义与调用封装。
- `repositories`：本地 markdown / json / memory 持久化。
- `models`：领域模型与接口模型。
- `core`：配置、日志、异常、基础设施。
- `benchmark` / `governance`：评测与治理。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app`

## 4. 前端整体分层

这一章解释前端不是单页脚本，而是一套调查工作台。

建议内容：
- 页面层：首页、输入分析页、战情页、调查工作台、历史页、设置页、资产页。
- 组件层：对话流、证据卡片、工具调用卡片、报告卡片、统计卡片。
- 服务层：API Client、WebSocket 订阅、时间格式化、状态整理。
- 视觉层：为什么会区分“资产映射 / 辩论过程 / 辩论结果 / 报告结果”。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/frontend/src`

## 5. 端到端主流程

这是整份 wiki 的主干章节，要把用户的一次分析请求完整讲清楚。

建议按时间线描述：
1. 用户输入故障描述、日志、堆栈和补充现象。
2. 后端创建 incident 和 debate session。
3. 责任田资产映射服务先命中特性/领域/聚合根/API/代码/数据库表。
4. 主 Agent 基于上下文进行初判并下发命令。
5. 专家 Agent 在命令门禁之下执行分析与工具调用。
6. Judge / Main Agent 收敛结论并生成报告。
7. WebSocket 事件流驱动前端展示资产映射、辩论过程、结论与报告。

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/flows/debate_flow.py`

## 6. API 与 WebSocket 入口

这一章解释“前后端是怎么连起来的”。

建议内容：
- REST 接口负责会话创建、历史查询、设置保存、资产上传、报告查询。
- WebSocket 负责实时事件流，包括阶段变化、Agent 发言、工具调用、结论和失败事件。
- 健康检查与配置接口如何用于前端启动和诊断。

重点说明：
- 为什么分析结果不能只靠轮询。
- 为什么事件模型是整个用户体验的核心。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/api`

## 7. 数据模型与仓储层

这一章解释系统保存了什么，以及为什么当前暂不依赖外部数据库。

建议内容：
- 会话模型：incident、debate session、report、evidence、timeline event。
- 配置模型：LLM 配置、工具配置、Agent 配置、Skill 配置。
- 资产模型：责任田、领域、聚合根、接口、数据库表、依赖服务。
- 仓储实现：本地 markdown、json、memory store 的使用边界。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/models`
- `/Users/neochen/multi-agent-cli_v2/backend/app/repositories`

## 8. 服务层编排

这一章解释 service 层不是简单 CRUD，而是业务能力的中枢。

建议重点拆解：
- `debate_service`：启动分析、驱动状态变化、终态收敛。
- `asset_service`：责任田资产加载、解析、映射。
- `report_service` / `report_generation_service`：最终结果整理与报告生成。
- `agent_tool_context_service`：给 Agent 注入允许访问的工具上下文。
- `agent_skill_service`：给 Agent 注入 Skill 摘要和能力提示。
- `feedback_service` / `remediation_service` / `governance service`：学习、修复与治理。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/services`

## 9. Flows 层

这一章要解释为什么还有 `flows` 这一层，以及它和 service 的区别。

建议内容：
- flow 负责把多个服务和 runtime 拼成一个业务场景。
- service 更像单领域能力，flow 更像用户旅程。
- `debate_flow` 如何承接输入上下文、发起 runtime、接收产物并落库。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/flows`

## 10. LangGraph 运行时核心

这是新版 wiki 的技术核心章节。

建议拆为几个小节：
- 图构建：GraphBuilder 如何定义节点和边。
- 状态：state、messages、phase、routing、outputs 如何组织。
- 节点：supervisor、expert agents、judge、aggregator。
- 执行：agent runner、phase executor、retry、timeout、degrade。
- 事件：event dispatcher 如何把运行时轨迹发给前端。
- 可靠性：checkpoint、resume、doom loop guard、session compaction。

关键目录与文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`

## 11. 多 Agent 角色与协作协议

这一章专门讲“有哪些 Agent、各自干什么、怎么配合”。

建议覆盖：
- `ProblemAnalysisAgent` / `MainAgent`：初判、命令分发、过程协调、最终收敛。
- `LogAgent`：日志、异常链路、时序、重试、网关/应用/基础设施异常。
- `CodeAgent`：代码入口、调用链、事务边界、重试、资源释放、潜在缺陷。
- `DomainAgent`：责任田、领域对象、业务流程、接口归属、变更影响面。
- `DatabaseAgent`：表结构、索引、锁等待、慢 SQL、连接与 session 信息。
- `CriticAgent`：反证、质疑、识别证据不足。
- `JudgeAgent`：比较候选根因、给出 Top-K 和置信度。

还要说明：
- 命令先行原则。
- 专家 Agent 不是自主随意出手，而是在主 Agent 指令下执行。
- Agent 间交流是通过显式消息与共享状态完成，不是简单串行独白。

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/specs.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/agents.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`

## 12. Prompt / Parser / Context Builder

这一章解释影响 Agent 质量的三件事：给了什么上下文、怎么组织提示词、怎么解析输出。

建议内容：
- system prompt、role prompt、command prompt 的分层。
- context builder 如何裁剪 incident 信息、责任田映射、历史结论、工具结果。
- parser 如何把模型输出转成结构化对象。
- 为什么必须优先结构化输出，而不是放任模型输出自由散文。

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompt_builder.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/parsers.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/context_builders.py`

## 13. 工具、Skill 与外部连接器

这一章需要把三类能力讲清楚，避免新读者混淆：
- Tool：运行时真正执行的动作。
- Skill：注入给 Agent 的能力说明与操作套路。
- Connector：接外部日志、代码仓、数据库、监控平台的适配器。

建议内容：
- LogAgent 读取本地日志文件与未来接日志平台的扩展方式。
- CodeAgent 访问本地仓库和远程 Git 仓库的方式。
- DomainAgent 解析责任田 Excel / markdown 资产。
- DatabaseAgent 读取 PostgreSQL 元信息的入口。
- 工具开关、命令门禁、调用审计、摘要化展示。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/tools`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/connectors`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime_ext`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_skill_service.py`

## 14. 可靠性、治理与安全

这一章解释为什么这个系统能用于生产环境，而不是只在 demo 场景里可跑。

建议内容：
- 超时、重试、降级、熔断、终态保证。
- 防止 pending 卡死的状态机保护。
- 工具权限与调用审计。
- Skill 注入边界与最小权限。
- 审批与治理入口。
- system card、风险动作、成本与配额治理。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/core`
- `/Users/neochen/multi-agent-cli_v2/backend/app/governance`
- `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph`

## 15. Benchmark 与评测体系

这一章要解释系统不是“看起来能跑”，而是有可量化质量门禁。

建议内容：
- Benchmark fixture 如何定义标准故障样本。
- Runner 如何跑批量评测。
- Scoring 如何评估命中率、Top-K、超时率、报告质量。
- 为什么要把 benchmark 接入 CI Gate。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/backend/app/benchmark`

## 16. 前端核心页面详解

建议按页面拆小节：
- `Home`：系统概览、入口、Agent 能力说明。
- `Incident`：用户输入故障信息并启动分析。
- `WarRoom`：战情态势、时间线、证据、关键结论同屏。
- `InvestigationWorkbench`：调查工作台，聚焦分析过程与结果比对。
- `History`：历史会话、回放和详情。
- `Settings` / `ToolsCenter` / `BenchmarkCenter` / `GovernanceCenter` / `Assets`：设置、工具、评测、治理、责任田维护。

关键目录：
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages`

## 17. 事件流与前端状态管理

这一章解释前端最复杂的一块：如何把后端事件流整理成用户可读的调查界面。

建议内容：
- 事件去重与顺序控制。
- Agent 对话消息、工具调用消息、阶段消息、报告消息的映射。
- 为什么要把资产映射、辩论过程、辩论结果、报告结果分开展示。
- 时间格式化、北京时间展示、流式追加与展开收起。

关键文件：
- `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`

## 18. 报告、证据链与结果组织

这一章讲最终用户最关心的结果页是怎么来的。

建议内容：
- Top-K 根因候选如何组织。
- 证据链如何关联日志、代码、责任田、数据库证据。
- 建议动作、风险说明、验证动作和回滚建议如何生成。
- 报告为什么不能只是一段 markdown，而要结构化、可视化、可对比。

关键文件：
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/report_generation_service.py`
- `/Users/neochen/multi-agent-cli_v2/backend/app/services/report_service.py`

## 19. 如何新增一个 Agent

这一章是给未来维护者的操作指南。

建议步骤：
1. 在文档中先定义角色、输入、输出、工具、治理要求。
2. 在 `specs.py` 中注册 Agent。
3. 增加 prompt、parser、node 执行逻辑。
4. 接入工具上下文或 skill。
5. 把前端展示补齐。
6. 增加 benchmark 用例与自测。

需要强调：
- 先改协议文档，再改代码。
- 新 Agent 必须遵守命令门禁、结构化输出与可审计原则。

## 20. 如何新增一个 Tool / Skill / Connector

这一章要把扩展路径拆清楚：

新增 Tool：
- 定义工具输入输出协议。
- 接入运行时工具注册与审计。
- 明确哪些 Agent 可用、在何种命令下可调用。

新增 Skill：
- 将方法论和操作套路写成可注入内容。
- 控制长度与命中条件。
- 为前端和日志增加命中审计信息。

新增 Connector：
- 定义外部平台访问适配器。
- 加入开关与降级逻辑。
- 在无真实数据源时支持本地文件模拟。

## 21. 本地运行、调试与排障

这一章应该是最实用的工程章节之一。

建议内容：
- 一键启动脚本与各服务端口。
- 后端、前端、运行日志、工具调用日志的路径。
- 常见问题：pending、TimeoutError、责任田未命中、工具调用失败、前端重复消息。
- 如何做 smoke test 和 benchmark。
- 出问题时建议的排查顺序。

关键入口：
- `/Users/neochen/multi-agent-cli_v2/scripts`
- `/Users/neochen/multi-agent-cli_v2/.run/logs`

## 22. 当前架构的已知复杂点与重构方向

这一章不是找借口，而是帮助开源读者理解系统的演化背景。

建议诚实列出：
- `langgraph_runtime.py` 和相关运行时代码仍然复杂。
- 某些服务与 runtime 的职责边界还可以继续收敛。
- prompt / parser / context builder 仍可继续模块化。
- 工具连接器和真实平台接入能力还在扩展中。
- 前端战情页和调查工作台的边界还要继续统一。

同时给出下一步方向：
- 进一步模块化 runtime。
- 用更标准的 checkpoint / replay / audit 模型。
- 增强真实数据源接入与回放测试。
- 提升报告与证据链可视化质量。

## 推荐写法约束

新版 code wiki 建议统一采用以下写法，确保可读性稳定：

每章固定包含：
- 这一章回答什么问题
- 关键文件入口
- 关键调用链
- 易错点 / 设计取舍
- 阅读建议

写作原则：
- 先讲主流程，再讲目录和模块。
- 先讲职责边界，再讲函数细节。
- 避免把 wiki 写成 API 索引或源码复制。
- 对复杂链路优先画图，再补文字说明。

## 建议后续拆分文档

如果开始正式撰写完整版 code wiki，建议把大文档拆成以下几个子文档：
- `docs/wiki/code-wiki-overview.md`
- `docs/wiki/code-wiki-backend.md`
- `docs/wiki/code-wiki-runtime.md`
- `docs/wiki/code-wiki-frontend.md`
- `docs/wiki/code-wiki-extension-guide.md`
- `docs/wiki/code-wiki-debugging.md`

这样可以避免单个文档过长，也更适合后续持续维护。
