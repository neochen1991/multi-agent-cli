# 2026-03-03 OpenDerisk 架构映射优化清单（执行版）

目标：严格参考本地 `OpenDerisk-main` 的架构和功能，重构本项目的多 Agent 生产故障根因分析能力。  
范围：当前阶段不引入外部数据库，优先本地文件与内存态。

---

## 一、OpenDerisk 参考基线（本地源码）

### 1. 分层架构（必须对齐）
- `core`：
  - `/Users/neochen/OpenDerisk-main/packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-core/src/derisk/agent/expand/react_master_agent/phase_manager.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-core/src/derisk/agent/expand/react_master_agent/work_log.py`
- `ext`：
  - `/Users/neochen/OpenDerisk-main/packages/derisk-ext/src/derisk_ext/agent/agents/open_rca/resource/open_rca_resource.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-ext/src/derisk_ext/agent/agents/open_rca/skills/open_rca_diagnosis/SKILL.md`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-ext/src/derisk_ext/mcp/gateway.py`
- `serve`：
  - `/Users/neochen/OpenDerisk-main/packages/derisk-serve/src/derisk_serve/agent/agents/controller.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat_async.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-serve/src/derisk_serve/mcp/api/endpoints.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-serve/src/derisk_serve/mcp/service/service.py`
- `app/client`：
  - `/Users/neochen/OpenDerisk-main/packages/derisk-app/src/derisk_app`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-client/src/derisk_client`

### 2. 核心功能（必须对齐）
- ReActMaster 增强链路：DoomLoop + Compaction + Prune + Truncation + WorkLog + PhaseManager + ReportGenerator  
参考：
  - `/Users/neochen/OpenDerisk-main/packages/derisk-core/src/derisk/agent/expand/react_master_agent/FEATURES.md`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-core/src/derisk/agent/expand/react_master_agent/README.md`
- MCP 生命周期管理：create/update/delete/start/offline/connect/list_tools/call_tool  
参考：
  - `/Users/neochen/OpenDerisk-main/packages/derisk-serve/src/derisk_serve/mcp/api/endpoints.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-serve/src/derisk_serve/mcp/service/service.py`
- 场景化 RCA Skill/Resource：参数化场景 + 规范化分析流程  
参考：
  - `/Users/neochen/OpenDerisk-main/packages/derisk-ext/src/derisk_ext/agent/agents/open_rca/resource/open_rca_resource.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-ext/src/derisk_ext/agent/agents/open_rca/skills/open_rca_diagnosis/SKILL.md`
- 多会话模式：quick/background/async  
参考：
  - `/Users/neochen/OpenDerisk-main/packages/derisk-serve/src/derisk_serve/agent/agents/controller.py`
  - `/Users/neochen/OpenDerisk-main/packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat_async.py`

---

## 二、差距矩阵（按 OpenDerisk 能力项）

- [x] 分层架构：当前 `backend/app/runtime` 仍偏“大模块拼接”，未形成 `core/ext/serve` 明确边界。
- [x] WorkLog：当前有 `trace_lineage`，但缺少 OpenDerisk 式“工作日志上下文注入”标准接口。
- [x] History Prune：已有 `session_compaction`，但缺少独立 prune 策略和可观测统计。
- [x] MCP 管理 API：当前是工具配置中心，不是完整 MCP 生命周期服务。
- [x] Skill 化 RCA：当前 prompt 分散，缺少 OpenRCA 那样的技能文档驱动流程。
- [x] 多会话模式：当前实时辩论单主流程，缺 quick/background/async 三态策略。

---

## 三、执行清单（按 OpenDerisk 架构改造）

## P0（最高优先，先把“架构骨架”和“调用链”做对）

### P0-1 建立 `core/ext/serve` 对齐目录与职责
- [x] 新建本项目分层边界：
  - `backend/app/runtime_core/`（ReActMaster 核心能力）
  - `backend/app/runtime_ext/`（技能、资源、连接器扩展）
  - `backend/app/runtime_serve/`（会话模式、路由、对外服务）
- [x] 将现有 LangGraph 编排器只保留“协调职责”，剥离执行细节到分层模块。
- OpenDerisk 对照：
  - `packages/derisk-core`
  - `packages/derisk-ext`
  - `packages/derisk-serve`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/`
- 验收：
  - 编排器文件不再承担 prompt/执行/日志/路由全部职责。

### P0-2 统一 Agent 创建与执行路径（仿 ReActMaster 入口）
- [x] 移除“Factory 与 execution 双轨”偏差，统一通过单入口执行。
- [x] 工具绑定、LLM 调用、结构化输出、重试全部走同一运行时。
- OpenDerisk 对照：
  - `react_master_agent.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/agents/factory.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/execution.py`
- 验收：
  - 任意 agent 调用均可在日志中追溯同一条标准执行链。

### P0-3 引入 WorkLog 上下文协议（替代零散状态拼接）
- [x] 增加 `WorkLogManager`：记录命令、工具调用、结果摘要、证据引用、失败原因。
- [x] 给主Agent/子Agent prompt 注入 `work_log_context` 而非手工拼接 `history_cards`。
- OpenDerisk 对照：
  - `work_log.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/trace_lineage/recorder.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/context_builders.py`
- 验收：
  - 前端和日志能看到“每轮决策引用了哪些工作记录”。

### P0-4 增加独立 Prune 模块（Compaction 之外）
- [x] 新增历史修剪策略：按 token 上限保留关键信息，压缩低价值重复消息。
- [x] 输出 prune 统计指标（修剪条数、节省 token）。
- OpenDerisk 对照：
  - `prune.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/session_compaction.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/message_ops.py`
- 验收：
  - 长会话中 token 增长曲线可控，且不丢失核心证据。

### P0-5 构建“命令驱动”的主从协作协议
- [x] 主Agent只发命令，不直接替子Agent产出结果。
- [x] 子Agent收到命令后决定是否调用工具，再回传结构化证据。
- OpenDerisk 对照：
  - ReActMaster 的 Task/Action 语义（`react_master_agent.py`）
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/mailbox.py`
- 验收：
  - 不再出现“主Agent有结果但子Agent只有收到命令”的展示断层。

## P1（高优先，对齐 OpenDerisk 的功能模块）

### P1-1 Skill 化 RCA（OpenRCA 方法论落地）
- [x] 新增本项目 RCA 技能文档（阶段、规则、禁止事项、输出规范）。
- [x] 将 prompt 构建改为“技能模板 + 场景参数”注入。
- OpenDerisk 对照：
  - `open_rca_diagnosis/SKILL.md`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompt_builder.py`
- 验收：
  - 新 incident 可复用同一 RCA 技能流程，不靠临时 prompt 调整。

### P1-2 Resource 化“责任田与资产映射”
- [x] 把领域责任田、接口映射、owner 清单封装为 `Resource` 抽象。
- [x] 支持按场景参数加载不同资产数据源（本地 md/csv/excel）。
- OpenDerisk 对照：
  - `open_rca_resource.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/asset_service.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/asset_knowledge_service.py`
- 验收：
  - “资产映射”页展示来自 Resource 的结构化结果，而非 prompt 文本提取。

### P1-3 MCP 生命周期管理接口（仿 serve/mcp）
- [x] 增加工具源管理 API：`create/update/delete/start/offline/health/list/run`。
- [x] 统一认证头、token 合并、调用审计记录。
- OpenDerisk 对照：
  - `mcp/api/endpoints.py`
  - `mcp/service/service.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/tooling_service.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/tool_registry/registry.py`
- 验收：
  - 工具开关之外，具备“服务化管理 + 可用性检测 + 调用治理”能力。

### P1-4 多会话模式（quick/background/async）
- [x] 新增三种执行策略：
  - quick：快速单轮摘要
  - background：断连后后台继续
  - async：立即返回 task_id，异步追踪
- OpenDerisk 对照：
  - `agent/agents/controller.py`
  - `agent/agents/chat/agent_chat_async.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/api/ws_debates.py`
- 验收：
  - 前端可选会话模式，断开连接不丢任务。

## P2（中高优先，补齐质量与交付能力）

### P2-1 报告生成器对齐（多格式+结构化）
- [x] 报告生成从单一 markdown 升级为：markdown/json/html（至少两种）。
- [x] 报告必须包含证据链、候选根因、置信度、待验证项。
- OpenDerisk 对照：
  - `report_generator.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/report_generation_service.py`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateResultPanel.tsx`
- 验收：
  - 报告页不再直接裸显示 md，支持结构化卡片。

### P2-2 工具输出截断与完整结果引用
- [x] 超大输出自动截断，完整结果保存到本地会话目录并返回引用 ID。
- [x] 前端支持“展开查看完整工具输出”。
- OpenDerisk 对照：
  - `truncation.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/output_truncation.py`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- 验收：
  - 不再因大输出污染上下文或导致前端卡顿。

### P2-3 Benchmark Gate 与稳定性基线
- [x] 基于 benchmark 场景建立 CI 门禁（超时率/失败率/空结论率）。
- [x] 失败自动阻断合并或发布流程。
- OpenDerisk 对照：
  - 工程实践层（非单文件功能）
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/scripts/`
  - `.github/workflows/*`
- 验收：
  - benchmark 可自动产出评分并可阻断回归。

## P3（中优先，前端交互与治理）

### P3-1 战情页对齐“调查工作台”体验
- [x] 资产映射、辩论过程、辩论结果、报告四屏一致化。
- [x] 时间线 + 证据链 + 工具调用 + 主Agent结论同屏联动。
- OpenDerisk 对照：
  - app/client 产品化思路（`derisk-app`, `derisk-client`）
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/WarRoom/index.tsx`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/*.tsx`
- 验收：
  - 用户可从同一页面追踪“命令 -> 工具 -> 证据 -> 结论”全链路。

### P3-2 治理与审计看板
- [x] 展示团队维度成功率、超时率、工具失败率、模型成本。
- [x] 支持按 session_id 回放关键决策路径。
- OpenDerisk 对照：
  - 服务化治理思路（mcp/service + 多会话控制）
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/governance_ops_service.py`
- 验收：
  - 可按租户/团队/时间窗查看治理指标。

### P3-3 前端功能对标 OpenDerisk（新增）
- [x] 建立前端“模块化页面能力”对标矩阵（不是只做样式）。
- [x] 将“对话流 + 工具面板 + 执行结果”拆分为独立可复用组件。
- [x] 对齐 MCP 管理页的“列表/详情/试运行”三段式交互。
- OpenDerisk 对照：
  - `/Users/neochen/OpenDerisk-main/web/src/app/chat/page.tsx`
  - `/Users/neochen/OpenDerisk-main/web/src/hooks/use-chat.ts`
  - `/Users/neochen/OpenDerisk-main/web/src/app/mcp/page.tsx`
  - `/Users/neochen/OpenDerisk-main/web/src/app/mcp/detail/page.tsx`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/ToolsCenter/index.tsx`
- 验收：
  - 辩论流、工具调用、结果回放为分层组件，不再混在单个页面状态里。
  - 工具中心支持“列表 -> 详情 -> 参数试跑 -> 结果展示”完整路径。

### P3-4 流式会话体验对标（OpenDerisk use-chat）
- [x] 统一前端流式协议处理，支持增量渲染、异常事件、终止事件。
- [x] 消息渲染层实现“缩略 + 展开全文”，默认展示关键信息。
- OpenDerisk 对照：
  - `/Users/neochen/OpenDerisk-main/web/src/hooks/use-chat.ts`
  - `/Users/neochen/OpenDerisk-main/web/src/contexts/chat-context.tsx`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/services/api.ts`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/WarRoom/index.tsx`
- 验收：
  - 不再出现重复消息/半截消息/JSON 原样泄露到聊天气泡。
  - 中断、重连、完成态在 UI 上可区分且状态一致。

### P3-5 首页与入口体验对标（OpenDerisk HomeChat）
- [x] 首页保留“agent能力介绍 + 快速入口 + 最近会话”三块核心信息。
- [x] 输入故障信息后在同页直接可启动分析，不跳转丢上下文。
- OpenDerisk 对照：
  - `/Users/neochen/OpenDerisk-main/web/src/app/page.tsx`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Home/index.tsx`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- 验收：
  - 首页信息不再是占位假数据；关键入口可点击并直达有效流程。

---

## 四、执行顺序（强制）

1. P0 全部完成后，才开始 P1。  
2. P1 完成后，才开始 P2。  
3. P2 完成后，才开始 P3。  
4. 每完成一项，在本文件勾选并追加“变更文件 + 自测结果”。

---

## 五、当前约束说明

- 当前阶段不引入外部存储；所有状态、日志、审计先用本地文件/内存。  
- LLM 保持当前 `kimi-k2.5` 配置，不做模型体系替换。  
- 优先保证“真实调用、可追踪、可恢复”，再做高级自治能力。

---

## 六、本轮实施记录（2026-03-03）

### 前端模块化能力对标矩阵

| OpenDerisk 页面能力 | 本项目页面 | 组件落点 |
| --- | --- | --- |
| Chat 流式会话（`web/src/app/chat/page.tsx` + `use-chat.ts`） | Incident 辩论过程 | `components/incident/DialogueFilterBar.tsx` + `components/incident/DialogueStream.tsx` + `components/incident/DebateProcessPanel.tsx` |
| MCP 列表/详情/试跑（`web/src/app/mcp/page.tsx` + `mcp/detail/page.tsx`） | ToolsCenter | `components/tools/ToolRegistryList.tsx` + `components/tools/ToolDetailPanel.tsx` + `components/tools/ToolTrialRunner.tsx` + `components/tools/ToolAuditPanel.tsx` |
| Home 快速进入会话（`web/src/app/page.tsx`） | Home | `pages/Home/index.tsx`（快速启动分析 + 最近会话 + Agent 介绍） |

- 后端新增工具试跑能力：
  - `/settings/tooling/registry/{tool_name}`
  - `/settings/tooling/trial-run`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/api/settings.py`
- 前端工具中心重构为“列表 -> 详情 -> 参数试跑 -> 审计查询”：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/pages/ToolsCenter/index.tsx`
  - 接口扩展：`/Users/neochen/multi-agent-cli_v2/frontend/src/services/api.ts`
- 辩论过程面板改为“事件明细优先”：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- 对话流文本解析增强（降低 JSON 泄露与重复表达）：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Incident/index.tsx`
- Incident 对话区组件化（筛选条与对话流拆分）：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DialogueFilterBar.tsx`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DialogueStream.tsx`
- 工具中心组件化（列表、详情、试跑、审计）：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/components/tools/ToolRegistryList.tsx`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/components/tools/ToolDetailPanel.tsx`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/components/tools/ToolTrialRunner.tsx`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/components/tools/ToolAuditPanel.tsx`
- 首页新增快速启动分析入口（创建 incident + session 后自动进入分析）：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/pages/Home/index.tsx`

### 治理看板补齐（P3-2 / 2026-03-03）

- 后端新增团队治理指标聚合（按团队统计成功率、超时率、工具失败率、模型成本估算）：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/services/governance_ops_service.py`
- 后端新增治理 API：
  - `GET /governance/team-metrics`
  - `GET /governance/session-replay/{session_id}`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/api/governance.py`
- 前端治理页新增：
  - 团队治理指标面板（支持时间窗切换）
  - session 回放面板（关键决策 + 时间线步骤）
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/services/api.ts`

### P2 既有能力核对（2026-03-03）

- 报告多格式输出与导出接口已具备：
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/backend/app/services/report_generation_service.py`
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/backend/app/api/reports.py`
- Benchmark Gate 已接入 CI：
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/.github/workflows/ci.yml`
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/scripts/benchmark-gate.py`

### P0 运行时能力补齐（2026-03-03）

- 统一 Agent 执行链路为 `langgraph/execution.py` 单入口，移除 orchestrator 中 factory 双轨入口：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/execution.py`
- 新增 WorkLog 协议并注入主Agent/子Agent prompt：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/work_log_manager.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompt_builder.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- 历史修剪策略增加统计输出（`history_pruned` 事件）：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/message_ops.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`

### P1 MCP 生命周期接口补齐（2026-03-03）

- 工具注册中心新增生命周期方法（create/update/delete/start/offline/health/run）：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/tool_registry/registry.py`
- 对外 API 新增工具生命周期路由：
  - `POST /settings/tooling/registry`
  - `PUT /settings/tooling/registry/{tool_name}`
  - `DELETE /settings/tooling/registry/{tool_name}`
  - `POST /settings/tooling/registry/{tool_name}/start`
  - `POST /settings/tooling/registry/{tool_name}/offline`
  - `GET /settings/tooling/registry/{tool_name}/health`
  - `POST /settings/tooling/registry/{tool_name}/run`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/api/settings.py`

### P1 Skill/Resource 对齐补齐（2026-03-03）

- 新增 RCA Skill 文档与模板注入：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/skills/open_rca_diagnosis/SKILL.md`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/rca_skill.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompt_builder.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
- 责任田与资产 Resource 化能力核对：
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/backend/app/services/asset_knowledge_service.py`
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/backend/app/services/asset_service.py`
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/backend/app/services/agent_tool_context_service.py`

### P0 主从命令协作能力核对（2026-03-03）

- 主Agent下发命令、子Agent按命令执行并反馈、工具调用受命令门禁控制：
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/mailbox.py`
  - 变更/核对文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`

### P1 多会话模式补齐（2026-03-03）

- 会话创建支持模式参数：`standard|quick|background|async`，`quick` 自动单轮：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/api/debates.py`
- 新增后台执行接口（断连后可持续运行）：
  - `POST /debates/{session_id}/execute-background`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/api/debates.py`
- 前端 API 增加模式透传与后台执行方法：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/services/api.ts`

### P0 分层边界补齐（2026-03-03）

- 新增 `runtime_core/runtime_ext/runtime_serve` 三层目录并导出核心能力：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_core/__init__.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_core/orchestrator.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_core/work_log.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_ext/__init__.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_ext/connectors.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_ext/resources.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_ext/tooling.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_serve/__init__.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime_serve/session_modes.py`
- 流程入口改用 `runtime_core` 导出（减少上层直接依赖 `runtime/langgraph_runtime.py`）：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/flows/debate_flow.py`

### P2 输出截断与引用补齐（2026-03-03）

- 超长输出落盘并返回 `ref_id`：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/output_truncation.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/execution.py`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph_runtime.py`
- 新增完整输出查询接口：
  - `GET /debates/output-refs/{ref_id}`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/backend/app/api/debates.py`
- 前端对话支持按 `ref_id` 拉取并展开完整输出：
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DialogueStream.tsx`
  - 变更文件：`/Users/neochen/multi-agent-cli_v2/frontend/src/services/api.ts`

### 本轮自测（2026-03-03）

- 后端语法检查：`cd /Users/neochen/multi-agent-cli_v2/backend && python3 -m compileall -q app`
- 后端运行时能力抽样：
  - `cd /Users/neochen/multi-agent-cli_v2/backend && ./.venv/bin/python - <<'PY' ...`
  - 验证项：`team_metrics` 可返回、输出截断可生成 `ref_id`、`ref_id` 可回查完整内容。
- 前端类型检查：`cd /Users/neochen/multi-agent-cli_v2/frontend && npm run typecheck`
- 前端构建：`cd /Users/neochen/multi-agent-cli_v2/frontend && npm run build`
