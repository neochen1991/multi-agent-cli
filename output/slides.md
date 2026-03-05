---
marp: true
size: 16:9
paginate: true
theme: default
---

# 多 Agent RCA 平台
## Code Wiki 到 PPT 的系统化讲解

- 主题：代码架构、调度机制、Skill 能力与扩展方法
- 受众：新加入项目的研发/SRE/测试同学
- 目标：20 分钟内建立可落地的代码认知地图

---

# 1. 项目目标：可控、可解释、可回放

- 这是“多 Agent 协作排障系统”，不是单轮对话机器人
- LLM 负责推理，系统负责流程与治理
- 三条硬目标：
  - 可控：主 Agent 先下命令，专家后执行
  - 可解释：工具调用与 Skill 命中可审计
  - 可回放：会话事件、断点与结论可恢复

---

# 2. 代码分层架构（从前端到运行时）

- Frontend：Incident / Settings 页面承接交互与配置
- API：`/debates`、`/settings/tooling`、WS 实时流
- Services：`debate_service`、`agent_tool_context_service`、`agent_skill_service`
- Runtime：LangGraph Orchestrator + Nodes + Routing + Execution
- Persistence：session store、lineage、tooling config

---

# 3. 端到端执行链路（一次会话）

- 用户在 Incident 发起分析
- DebateService 先做资产采集与上下文压缩
- Orchestrator 启动 LangGraph 执行
- 各 Agent 走：命令 -> 工具/Skill -> LLM -> 结构化输出
- 事件流实时推送前端，最终落地报告

---

# 4. LangGraph 图：核心节点拓扑

- 主链：`init_session -> round_start -> supervisor_decide`
- 执行节点：
  - `analysis_parallel_node`
  - `analysis_collaboration_node`（可开关）
  - `speak:agent` 节点
- 收敛链：`round_evaluate -> (round_start | finalize)`
- 关键状态：`next_step`、`continue_next_round`

---

# 5. 调度机制：HybridRouter 怎么做决定

- Stage 1：Seeded（先用主 Agent 开场预置步骤）
- Stage 2：Consensus shortcut（Judge 高置信快速收敛）
- Stage 3：分析覆盖后强制进入 Critic/Rebuttal/Judge
- Stage 4：预算保护（步数超限回退规则路由）
- Stage 5：动态 LLM 路由
- Stage 6：异常兜底 rule-based + guardrail

---

# 6. Agent 体系：13 个角色分工

- Coordination：ProblemAnalysisAgent
- Analysis：Log / Domain / Code / Database / Metrics / Change / Runbook / RuleSuggestion
- Critique：Critic -> Rebuttal
- Judgment：Judge
- Verification：Verification

关键点：每个 Agent 是“职责明确 + 可插拔工具 + 可注入 Skill”的执行单元。

---

# 7. 单个 Agent 的运行流水线（最重要）

- 接收命令：`task/focus/expected_output/use_tool/skill_hints`
- 命令门禁：`command_gate` 判断是否允许工具/Skill
- 构建工具上下文：日志、代码、数据库、指标等
- 合并 Skill 上下文：按 hints 或文本匹配命中
- 调用 LLM：超时、重试、队列、降级
- 归一化输出：结构化 JSON + 证据链
- 回写状态：turn、mailbox、事件流

---

# 8. Skill 能力：配置入口与生效路径

- 配置模型：`AgentSkillConfig`
  - `enabled / skills_dir / max_skills / max_skill_chars / allowed_agents`
- 前端入口：`/settings` -> Agent Skill Router 配置卡片
- 后端接口：`GET/PUT /api/v1/settings/tooling`
- 持久化：`tooling_config.json`
- 运行时读取：`tooling_service.get_config()`

---

# 9. Skill 选择逻辑：如何命中

- 优先级 1：命令显式 `skill_hints`
- 优先级 2：运行时自动补 hints（按 agent + incident 信号）
- 优先级 3：文本匹配打分（task/focus/expected_output + triggers）
- 前置条件：
  - `skills.enabled=true`
  - agent 在允许列表
  - `has_command && allow_tool=true`

产出：`tool_context.data.skill_context` + `agent_skill_router` 审计日志

---

# 10. 可靠性治理：系统如何避免“卡死/乱跑”

- LLM 调用治理：超时计划、重试、队列控制、fallback turn
- 调度治理：rule engine 防重复、防超预算、防低信号循环
- 终态治理：会话必须进入 `completed/failed/cancelled`
- 结论治理：可配置“拒绝占位结论”门禁
- 可恢复治理：events/sessions/tasks + WS resume/snapshot

---

# 11. 审计与可观测：如何追踪一次分析

- 关键事件：
  - `agent_command_issued`
  - `agent_tool_context_prepared`
  - `agent_tool_io`
  - `agent_command_feedback`
  - `supervisor_decision`
- 技术意义：能追“谁下命令、谁调工具、命中什么 Skill、最终如何收敛”
- 前端视图：Incident 页面可看 Skill 路由与工具审计

---

# 12. 如何扩展新 Agent（工程路径）

1. 更新协议文档（agent-catalog / protocol-contracts）
2. `specs.py` 增 AgentSpec
3. `builder.py + routing_helpers.py` 增节点映射
4. `agent_tool_context_service.py` 增工具上下文分支
5. 新增对应 Skill，并设置 `agents:`
6. 放开 `allowed_agents` 配置
7. 补测试与回归验证

---

# 13. 如何扩展新 Skill（工程路径）

1. 新建 `backend/skills/<skill-name>/SKILL.md`
2. 写 front matter：`name/description/triggers/agents`
3. 写正文：Goal / Checklist / Output Contract
4. 用 `skill_hints` 做命中验证
5. 在 Incident 页面检查 `agent_skill_router` 审计

---

# 14. 总结与落地建议

- 这套系统本质是“四层流水线”：
  - 主 Agent 指挥
  - 工具 + Skill 提供证据与方法模板
  - LLM 推理产出结构化结论
  - 系统层负责审计、收敛、回放、终态
- 新人上手建议：
  - 先读 `langgraph_runtime.py` 与 `agent_tool_context_service.py`
  - 再看 `agent_skill_service.py` 与 Settings 配置链路
  - 最后结合 Incident 事件流做一次端到端跟踪
