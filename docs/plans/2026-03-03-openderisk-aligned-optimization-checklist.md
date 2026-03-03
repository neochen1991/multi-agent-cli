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

- [ ] 分层架构：当前 `backend/app/runtime` 仍偏“大模块拼接”，未形成 `core/ext/serve` 明确边界。
- [ ] WorkLog：当前有 `trace_lineage`，但缺少 OpenDerisk 式“工作日志上下文注入”标准接口。
- [ ] History Prune：已有 `session_compaction`，但缺少独立 prune 策略和可观测统计。
- [ ] MCP 管理 API：当前是工具配置中心，不是完整 MCP 生命周期服务。
- [ ] Skill 化 RCA：当前 prompt 分散，缺少 OpenRCA 那样的技能文档驱动流程。
- [ ] 多会话模式：当前实时辩论单主流程，缺 quick/background/async 三态策略。

---

## 三、执行清单（按 OpenDerisk 架构改造）

## P0（最高优先，先把“架构骨架”和“调用链”做对）

### P0-1 建立 `core/ext/serve` 对齐目录与职责
- [ ] 新建本项目分层边界：
  - `backend/app/runtime_core/`（ReActMaster 核心能力）
  - `backend/app/runtime_ext/`（技能、资源、连接器扩展）
  - `backend/app/runtime_serve/`（会话模式、路由、对外服务）
- [ ] 将现有 LangGraph 编排器只保留“协调职责”，剥离执行细节到分层模块。
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
- [ ] 移除“Factory 与 execution 双轨”偏差，统一通过单入口执行。
- [ ] 工具绑定、LLM 调用、结构化输出、重试全部走同一运行时。
- OpenDerisk 对照：
  - `react_master_agent.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/agents/factory.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/execution.py`
- 验收：
  - 任意 agent 调用均可在日志中追溯同一条标准执行链。

### P0-3 引入 WorkLog 上下文协议（替代零散状态拼接）
- [ ] 增加 `WorkLogManager`：记录命令、工具调用、结果摘要、证据引用、失败原因。
- [ ] 给主Agent/子Agent prompt 注入 `work_log_context` 而非手工拼接 `history_cards`。
- OpenDerisk 对照：
  - `work_log.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/trace_lineage/recorder.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/context_builders.py`
- 验收：
  - 前端和日志能看到“每轮决策引用了哪些工作记录”。

### P0-4 增加独立 Prune 模块（Compaction 之外）
- [ ] 新增历史修剪策略：按 token 上限保留关键信息，压缩低价值重复消息。
- [ ] 输出 prune 统计指标（修剪条数、节省 token）。
- OpenDerisk 对照：
  - `prune.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/session_compaction.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/message_ops.py`
- 验收：
  - 长会话中 token 增长曲线可控，且不丢失核心证据。

### P0-5 构建“命令驱动”的主从协作协议
- [ ] 主Agent只发命令，不直接替子Agent产出结果。
- [ ] 子Agent收到命令后决定是否调用工具，再回传结构化证据。
- OpenDerisk 对照：
  - ReActMaster 的 Task/Action 语义（`react_master_agent.py`）
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/nodes/supervisor.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/mailbox.py`
- 验收：
  - 不再出现“主Agent有结果但子Agent只有收到命令”的展示断层。

## P1（高优先，对齐 OpenDerisk 的功能模块）

### P1-1 Skill 化 RCA（OpenRCA 方法论落地）
- [ ] 新增本项目 RCA 技能文档（阶段、规则、禁止事项、输出规范）。
- [ ] 将 prompt 构建改为“技能模板 + 场景参数”注入。
- OpenDerisk 对照：
  - `open_rca_diagnosis/SKILL.md`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompts.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/prompt_builder.py`
- 验收：
  - 新 incident 可复用同一 RCA 技能流程，不靠临时 prompt 调整。

### P1-2 Resource 化“责任田与资产映射”
- [ ] 把领域责任田、接口映射、owner 清单封装为 `Resource` 抽象。
- [ ] 支持按场景参数加载不同资产数据源（本地 md/csv/excel）。
- OpenDerisk 对照：
  - `open_rca_resource.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/asset_service.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/asset_knowledge_service.py`
- 验收：
  - “资产映射”页展示来自 Resource 的结构化结果，而非 prompt 文本提取。

### P1-3 MCP 生命周期管理接口（仿 serve/mcp）
- [ ] 增加工具源管理 API：`create/update/delete/start/offline/health/list/run`。
- [ ] 统一认证头、token 合并、调用审计记录。
- OpenDerisk 对照：
  - `mcp/api/endpoints.py`
  - `mcp/service/service.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/tooling_service.py`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/tool_registry/registry.py`
- 验收：
  - 工具开关之外，具备“服务化管理 + 可用性检测 + 调用治理”能力。

### P1-4 多会话模式（quick/background/async）
- [ ] 新增三种执行策略：
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
- [ ] 报告生成从单一 markdown 升级为：markdown/json/html（至少两种）。
- [ ] 报告必须包含证据链、候选根因、置信度、待验证项。
- OpenDerisk 对照：
  - `report_generator.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/report_generation_service.py`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateResultPanel.tsx`
- 验收：
  - 报告页不再直接裸显示 md，支持结构化卡片。

### P2-2 工具输出截断与完整结果引用
- [ ] 超大输出自动截断，完整结果保存到本地会话目录并返回引用 ID。
- [ ] 前端支持“展开查看完整工具输出”。
- OpenDerisk 对照：
  - `truncation.py`
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/output_truncation.py`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/DebateProcessPanel.tsx`
- 验收：
  - 不再因大输出污染上下文或导致前端卡顿。

### P2-3 Benchmark Gate 与稳定性基线
- [ ] 基于 benchmark 场景建立 CI 门禁（超时率/失败率/空结论率）。
- [ ] 失败自动阻断合并或发布流程。
- OpenDerisk 对照：
  - 工程实践层（非单文件功能）
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/scripts/`
  - `.github/workflows/*`
- 验收：
  - benchmark 可自动产出评分并可阻断回归。

## P3（中优先，前端交互与治理）

### P3-1 战情页对齐“调查工作台”体验
- [ ] 资产映射、辩论过程、辩论结果、报告四屏一致化。
- [ ] 时间线 + 证据链 + 工具调用 + 主Agent结论同屏联动。
- OpenDerisk 对照：
  - app/client 产品化思路（`derisk-app`, `derisk-client`）
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/WarRoom/index.tsx`
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/components/incident/*.tsx`
- 验收：
  - 用户可从同一页面追踪“命令 -> 工具 -> 证据 -> 结论”全链路。

### P3-2 治理与审计看板
- [ ] 展示团队维度成功率、超时率、工具失败率、模型成本。
- [ ] 支持按 session_id 回放关键决策路径。
- OpenDerisk 对照：
  - 服务化治理思路（mcp/service + 多会话控制）
- 本项目落点：
  - `/Users/neochen/multi-agent-cli_v2/frontend/src/pages/GovernanceCenter/index.tsx`
  - `/Users/neochen/multi-agent-cli_v2/backend/app/services/governance_ops_service.py`
- 验收：
  - 可按租户/团队/时间窗查看治理指标。

### P3-3 前端功能对标 OpenDerisk（新增）
- [ ] 建立前端“模块化页面能力”对标矩阵（不是只做样式）。
- [ ] 将“对话流 + 工具面板 + 执行结果”拆分为独立可复用组件。
- [ ] 对齐 MCP 管理页的“列表/详情/试运行”三段式交互。
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
- [ ] 统一前端流式协议处理，支持增量渲染、异常事件、终止事件。
- [ ] 消息渲染层实现“缩略 + 展开全文”，默认展示关键信息。
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
- [ ] 首页保留“agent能力介绍 + 快速入口 + 最近会话”三块核心信息。
- [ ] 输入故障信息后在同页直接可启动分析，不跳转丢上下文。
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
