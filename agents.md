# AGENTS.md

本文件采用 Harness Engineering 思路，只保留“高价值导航 + 强约束入口”，不承载全部细节。

## 1. 目标与边界

- 目标：构建可控、可解释、可回放的生产问题根因分析多 Agent 系统。
- 系统边界：主 Agent 负责调度与收敛；专家 Agent 负责证据分析；工具调用受命令门禁与开关控制。
- Repo 是唯一事实源：所有协议、规则、流程、评测都必须落库到仓库文档与代码。

## 2. 快速导航

- 架构与流程图：
  - `docs/architecture/system-architecture-overview.svg`
  - `docs/architecture/business-process-flow.svg`
- Agent 详细规范：
  - `docs/agents/agent-catalog.md`
  - `docs/agents/protocol-contracts.md`
  - `docs/agents/tooling-and-audit.md`
  - `docs/agents/reliability-governance.md`
  - `docs/agents/checkpoint-resume.md`
- 计划与执行清单：
  - `docs/plans/2026-03-05-industry-sre-benchmark-gap-remediation-plan.md`
  - `docs/plans/2026-03-04-industry-benchmark-gap-execution-checklist.md`

## 3. 运行时硬约束（必须满足）

1. 主 Agent 命令先行：先有 `agent_command_issued`，后有专家执行。
2. 工具调用可审计：每次调用必须有 `command_gate`、请求摘要、返回摘要、状态与耗时。
3. Skill 调用可审计：每次命中的本地 Skill 必须记录命中来源、Skill 名称、目录与注入内容摘要。
4. 结构化输出优先：关键 Agent 输出必须可解析，不允许仅自然语言散文。
5. 有效结论门禁：若启用 `DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION=true`，最终报告禁止“需要进一步分析”作为根因结论。
6. 会话可终止：任何异常不得长期 `pending`，必须进入终态并给出原因。
7. 断点续写：会话中断后必须能恢复，优先读取 markdown 断点文件。

## 4. Harness Engineering 落地原则

1. Humans steer, agents execute：
   - 人定义约束、策略、评测、治理。
   - Agent 在约束内执行，不直接替代系统控制逻辑。
2. Model 与 System 分层：
   - LLM 负责推理生成。
   - 系统负责状态机、路由、超时、重试、降级、审计。
3. Trajectory-first：
   - 不只看最终结论，要可回放完整轨迹（命令、工具、证据、裁决）。
4. Mechanical sympathy：
   - 用 CI Gate 与脚本检查强制规范，避免文档和实现漂移。

## 5. 文档维护策略

- 本文件控制在轻量规模（导航 + 约束），避免膨胀成“百科全书”。
- 新增细节应写入 `docs/agents/*`，并在此添加链接。
- 每次改动 Agent 协议/角色/路由策略，必须同步更新对应文档。
- CI 会执行 `scripts/check-agents-md.py` 做基础守护：
  - `AGENTS.md` 行数上限检查
  - 关键链接存在性检查
  - 必备约束条目检查

## 6. 实现入口

- Runtime 主入口：`backend/app/runtime/langgraph_runtime.py`
- Graph 构建：`backend/app/runtime/langgraph/builder.py`
- Agent 节点：`backend/app/runtime/langgraph/nodes/agents.py`
- Supervisor 路由：`backend/app/runtime/langgraph/nodes/supervisor.py`
- Agent 执行：`backend/app/runtime/langgraph/execution.py`
- 工具上下文：`backend/app/services/agent_tool_context_service.py`
- Skill 路由：`backend/app/services/agent_skill_service.py`
- 前端分析页：`frontend/src/pages/Incident/index.tsx`

---

如需扩展新 Agent，请先更新 `docs/agents/agent-catalog.md` 与 `docs/agents/protocol-contracts.md`，再改代码。
