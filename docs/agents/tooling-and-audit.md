# Tooling And Audit

## 1. Scope

本文件定义多 Agent 运行时中的工具门禁、工具上下文、工具审计与 Skill 审计的最小规范。

适用范围：
- `AgentToolContextService`
- `backend/app/services/tool_context/*`
- `backend/app/runtime/langgraph_runtime.py`
- `backend/app/runtime/langgraph/event_dispatcher.py`
- 前端 Investigation / WarRoom 的工具回放视图

## 2. Design Goals

1. 工具调用必须先过命令门禁，再执行。
2. Agent 看到的 focused context 必须可解释、可回放、可裁剪。
3. 工具开关关闭时必须优雅降级，而不是无声失败。
4. 每次工具或 Skill 命中都要留下结构化审计痕迹。

## 3. Runtime Flow

一次标准工具链路按以下顺序发生：

1. 主 Agent 先发出 `agent_command_issued`
2. `AgentToolContextService.build_context(...)` 进入 router / provider / assembler
3. 运行时发出 `agent_tool_context_prepared`
4. 具体工具执行前后发出 `agent_tool_io`
5. lineage / replay 层将其归一化为 `tool_audit`
6. 若命中本地 Skill，同时发出 `skill_hit`

不允许跳过第 1 步直接让专家 Agent 执行高风险工具。

## 4. Tool Context Structure

`agent_tool_context_prepared` 至少应包含：

- `agent_name`
- `tool_name`
- `status`
- `summary`
- `command_gate`
- `data_preview`
- `focused_preview`

推荐字段：

- `data_detail`
- `focused_detail`
- `audit_log`
- `execution_path`
- `permission_decision`

约束：

- `data_preview` 面向事件流和前端，应保持紧凑。
- `data_detail` 允许更完整，但仍应避免直接转储超大原文。
- `focused_preview` 应优先表达当前 Agent 真正需要的证据切片。

## 5. Command Gate Rules

门禁决策至少需要回答三件事：

1. 当前 Agent 是否收到主 Agent 命令。
2. 命令是否显式允许或禁止工具。
3. 决策来源是显式布尔、默认策略还是配置禁用。

建议稳定字段：

- `allow_tool`
- `reason`
- `decision_source`
- `has_command`

当工具被禁用时，也要发出可回放事件，不能只在日志里静默记录。

## 6. Tool Audit Rules

每次工具调用都应能还原以下事实：

- 谁调的：`agent_name`
- 调了什么：`tool_name`
- 为什么能调：`command_gate`
- 请求是什么：`request_summary`
- 返回了什么：`response_summary`
- 是否成功：`status`
- 花了多久：`duration_ms`

推荐事件组合：

- `agent_tool_context_prepared`
- `agent_tool_io`
- `tool_audit`

其中：

- `agent_tool_io` 更贴近运行时原始轨迹
- `tool_audit` 更适合 lineage、治理与前端统一展示

## 7. Skill Audit Rules

每次命中本地 Skill 必须记录：

- `agent_name`
- `skill_name`
- `skill_dir`
- `selection_source`

推荐补充：

- `matched_signals`
- `injection_summary`

禁止把完整 Skill 文本直接塞进事件体；只记录命中原因与注入摘要。

## 8. Analysis Depth Interaction

`analysis_depth_mode` 会影响工具策略，但不改变工具审计要求。

当前约定：

- `quick`: 默认 1 轮，focused context 更激进裁剪，优先高信号工具和最短闭环。
- `standard`: 默认 2 轮，允许一轮追问与交叉验证。
- `deep`: 默认 4 轮，允许更长证据链、更丰富的 Top-K 候选和更严格的覆盖检查。

无论是哪种深度模式，工具审计字段都必须保持兼容。

## 9. Frontend Expectations

前端至少依赖以下结果：

- 工具是否启用
- command gate 的理由
- focused context 预览
- 关键工具返回摘要
- Skill 命中记录

因此事件字段命名应优先稳定，而不是把语义藏在自然语言 summary 里。
# Tooling And Audit

当前 runtime 在 replay / audit 维度需要同时保证两件事：

- 工具与 skill 命中的事实可追溯
- Agent 实际看到的上下文边界可解释

因此 `agent_tool_context_prepared` 事件除了保留原有的 `tool_name / status / command_gate / data_preview / focused_preview` 外，还需要继续稳定支持：

- `permission_decision`
- `execution_path`
- 与 Prompt context envelope 一致的 focused/shared 视角解释

这保证了后续即使 Prompt 不再直接打印原始 `incident/context` 全量对象，回放页仍能解释“Agent 当时看到了什么、为什么这么判断”。
