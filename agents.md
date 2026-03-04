# Agents.md

本文件定义本项目 Multi-Agent 体系的设计规范、协作协议与工程约束。  
目标：让 `生产问题根因分析` 场景中的 Agent 行为可控、可解释、可审计、可持续优化。

---

## 1. 设计目标

1. 快速定位：针对生产故障在单次会话内输出可执行结论。  
2. 证据闭环：结论必须可回溯到日志/代码/领域/指标证据。  
3. 可运营：支持超时降级、失败恢复、回放复盘、基准评测。  
4. 可扩展：新增 Agent 或工具时，不破坏现有协作协议。
5. 可恢复：必须支持断点续写，且断点信息使用 `md` 文档持久化。

---

## 2. 业界最佳实践（落地版）

1. 单一职责：每个 Agent 只负责一个明确视角，不做“全能分析”。  
2. 主控-专家模式：由主 Agent 统一调度，专家按命令执行。  
3. 契约优先：输出必须遵循 JSON Schema，禁止自由散文式返回。  
4. 证据优先：观点必须附证据链，不允许“仅凭经验”下结论。  
5. 工具门禁：工具调用必须有主 Agent 命令授权，并记录审计轨迹。  
6. 有界上下文：每轮仅保留关键历史，避免上下文膨胀和重复。  
7. 韧性优先：超时重试、局部降级、不中断全局流程。  
8. 可观测优先：全链路事件、时间戳、调用路径可追踪。  
9. 基准驱动：用 benchmark 指标持续评估正确率与稳定性。

---

## 3. 系统中的 Agent 组件

### 3.1 主控 Agent

- `ProblemAnalysisAgent`（phase=`coordination`）  
  - 职责：问题拆解、命令分发、轮次推进、收敛判断。  
  - 输出重点：`commands[]`, `next_mode`, `next_agent`, `should_stop`.

### 3.2 分析专家 Agent（phase=`analysis`）

- `LogAgent`：日志时序、错误模式、异常链路  
- `DomainAgent`：接口-领域-聚合根-责任田映射  
- `CodeAgent`：代码路径、热点实现、风险变更  
- `MetricsAgent`：CPU/线程/连接池/错误率等指标侧证据  
- `ChangeAgent`：故障时间窗内变更关联分析  
- `RunbookAgent`：案例库匹配与处置SOP建议  
- `RuleSuggestionAgent`：告警规则与阈值建议

### 3.3 对抗与裁决 Agent

- `CriticAgent`（phase=`critique`）：质疑证据缺口与逻辑漏洞  
- `RebuttalAgent`（phase=`rebuttal`）：回应质疑并补强证据  
- `JudgeAgent`（phase=`judgment`）：综合裁决与最终结论  
- `VerificationAgent`（phase=`verification`）：验证计划与回归检查项

---

## 4. 协作协议（必须遵守）

1. 主 Agent 先发命令（`agent_command_issued`）。  
2. 专家 Agent 接到命令后执行分析。  
3. 若命令允许工具调用，才可使用工具。  
4. 专家输出必须包含：`chat_message + analysis + conclusion + confidence + evidence_chain`。  
5. 质疑/反驳阶段必须引用已有证据，不可重复完整分析。  
6. Judge 仅在关键专家观点具备后进入裁决。  
7. 若配置要求有效结论（`DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION=true`），禁止输出“需要进一步分析”作为最终报告结论。

---

## 5. 输入输出契约（Schema-first）

### 5.1 主 Agent 命令输出（简化）

```json
{
  "chat_message": "会议主持发言",
  "analysis": "当前判断",
  "conclusion": "阶段结论",
  "next_mode": "parallel_analysis|single|judge|stop",
  "next_agent": "LogAgent|DomainAgent|...",
  "should_stop": false,
  "stop_reason": "",
  "commands": [
    {
      "target_agent": "CodeAgent",
      "task": "定位连接池耗尽根因",
      "focus": "事务边界与连接释放",
      "expected_output": "代码证据+风险评估",
      "use_tool": true
    }
  ],
  "evidence_chain": [],
  "confidence": 0.0
}
```

### 5.2 专家 Agent 标准输出（简化）

```json
{
  "chat_message": "先给会议发言",
  "analysis": "分析过程",
  "conclusion": "本Agent结论",
  "confidence": 0.73,
  "evidence_chain": [
    {
      "description": "证据描述",
      "source": "log|code|domain|metrics",
      "source_ref": "文件/接口/traceId"
    }
  ],
  "open_questions": []
}
```

### 5.3 Judge 输出（简化）

```json
{
  "final_judgment": {
    "root_cause": { "summary": "", "category": "", "confidence": 0.0 },
    "evidence_chain": [],
    "fix_recommendation": { "summary": "", "steps": [] },
    "impact_analysis": { "affected_services": [], "business_impact": "" },
    "risk_assessment": { "risk_level": "high|medium|low", "risk_factors": [] }
  },
  "decision_rationale": { "key_factors": [], "reasoning": "" },
  "confidence": 0.0
}
```

---

## 6. 工具调用规范

1. 工具调用由 `AgentToolContextService` 统一管理。  
2. 每次调用必须有 `command_gate` 判定结果。  
3. 工具开启条件：  
   - 该 Agent 工具配置 `enabled=true`  
   - 主 Agent 命令允许（`use_tool=true` 或可推断为允许）  
4. 必须写审计字段：`tool_name/action/status/detail/permission_decision/execution_path`。  
5. 失败时必须回退默认分析并显式输出失败原因，禁止静默吞错。  

---

## 7. 运行策略与可靠性

1. 轮次：默认 `DEBATE_MAX_ROUNDS=1`，可配置。  
2. 执行模式：`standard | quick | background | async`。  
3. 并发：分析阶段支持并行执行（PhaseExecutor）。  
4. 超时：按 Agent/阶段配置 timeout 计划。  
5. 重试：仅重试可恢复错误（例如 timeout/rate limit）。  
6. 降级：单 Agent 失败不阻断全局；必须产出 fallback turn。  
7. 状态机：仅允许合法状态迁移，防止会话卡死。

---

## 8. 断点续写能力（MD 持久化，强制）

### 8.1 持久化要求

1. 每个会话必须落一份 Markdown 断点文件。  
2. 建议路径：`{LOCAL_STORE_DIR}/runtime/checkpoints/{session_id}.md`。  
3. 文件必须使用 UTF-8，且必须包含可机器读取的结构化区块（推荐 YAML Front Matter）。

### 8.2 断点文件最小内容

1. 会话标识：`session_id`、`incident_id`、`trace_id`。  
2. 进度状态：`status`、`current_phase`、`current_round`、`updated_at`。  
3. 已完成 Agent 列表与未完成任务列表。  
4. 最新主结论摘要、Top-K 候选摘要、关键证据摘要。  
5. 恢复指令：下一步建议执行的 `next_step` 与 `resume_hint`。

### 8.3 写入时机（至少）

1. `session_created` 后初始化断点文件。  
2. 每轮 `round_completed` 后增量更新。  
3. `session_failed` / `session_cancelled` 时写入最后快照。  
4. `session_completed` 时写入最终状态并标记归档。

### 8.4 恢复流程规范

1. 恢复时优先读取 `md` 断点文件。  
2. 解析出 `current_phase/current_round/next_step` 后继续执行。  
3. 若 `md` 缺失或损坏，回退到 JSON 会话存储恢复。  
4. 恢复后必须写一条审计事件：`session_resumed_from_checkpoint`。

### 8.5 标准模板（示例）

```md
---
session_id: deb_xxx
incident_id: inc_xxx
trace_id: trc_xxx
status: running
current_phase: analysis
current_round: 1
next_step: "speak:CodeAgent"
updated_at: "2026-03-04T16:00:00+08:00"
---

# 断点摘要
- 主结论：...
- Top-K：...
- 关键证据：...

## 已完成Agent
- LogAgent
- DomainAgent

## 待执行任务
- CodeAgent: 定位事务边界与连接释放问题
- JudgeAgent: 汇总裁决

## 恢复提示
从 `next_step` 继续，不重复执行已完成Agent。
```

---

## 9. 可观测与审计

必须记录以下事件（最小集）：

1. `session_created/session_started/session_completed/session_failed`  
2. `phase_changed/round_started/round_completed`  
3. `agent_command_issued/agent_command_feedback`  
4. `llm_call_started/llm_call_timeout/llm_call_failed/llm_call_succeeded`  
5. `agent_tool_context_prepared/agent_tool_io/agent_tool_context_failed`  
6. `result_ready/report_generated`

前端必须能展示：  
- 资产映射结果  
- 辩论过程（发言 + 工具调用）  
- 裁决结果与报告摘要  
- 关键决策回放（lineage）

---

## 10. 质量指标（SLO / Benchmark）

建议最小指标集：

1. Top1 命中率  
2. Top3 命中率  
3. 超时率（session/agent）  
4. 空结论率  
5. 工具调用成功率  
6. 平均分析时长与P95时长

发布前建议 Gate：

1. 超时率超过阈值 -> 阻断  
2. 空结论率超过阈值 -> 阻断  
3. Top1/Top3 低于基线 -> 阻断

---

## 11. 新增 Agent 的准入清单

新增 Agent 前必须满足：

1. 明确职责边界（不可与现有 Agent 重叠严重）。  
2. 定义 phase 与触发条件。  
3. 定义工具需求与门禁策略。  
4. 定义 JSON 输出契约。  
5. 加入路由策略与回退策略。  
6. 加入前端展示映射。  
7. 补充 benchmark 样例与失败样例。  

---

## 12. 禁止事项

1. 禁止主 Agent 直接替专家 Agent 产出专家结论。  
2. 禁止无命令工具调用。  
3. 禁止专家 Agent 输出超长无结构文本。  
4. 禁止最终报告缺少证据链与置信度。  
5. 禁止发生错误后无事件、无日志、无回退。

---

## 13. 文件对齐（当前实现）

关键实现位置：

- `backend/app/runtime/langgraph/specs.py`  
- `backend/app/runtime/langgraph_runtime.py`  
- `backend/app/runtime/langgraph/builder.py`  
- `backend/app/runtime/langgraph/nodes/supervisor.py`  
- `backend/app/runtime/langgraph/nodes/agents.py`  
- `backend/app/runtime/langgraph/phase_executor.py`  
- `backend/app/runtime/langgraph/execution.py`  
- `backend/app/services/agent_tool_context_service.py`

本文件应与上述实现保持同步更新。
