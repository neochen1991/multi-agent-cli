# Agent Catalog

## 1. 主控 Agent

- `ProblemAnalysisAgent`
  - phase: `coordination`
  - 职责：拆解问题、分发命令、推进讨论、触发收敛。
  - 深度能力：根据 `analysis_depth_mode` 和当前证据覆盖情况决定 `quick / standard / deep` 下的默认轮次、追问强度和停止条件。
  - 分发原则：主 Agent 只给高层任务方向；系统会把责任田映射出的 `api_endpoints / code_artifacts / class_names / database_tables / monitor_items / dependency_services / trace_ids / error_keywords` 自动注入到各子 Agent 的命令与工具上下文。
  - 关键输出：`selected_agents`、`commands`、`next_mode`、`next_agent`、`should_stop`、`stop_reason`、`top_k_hypotheses`、`evidence_coverage`、`convergence_score`。
  - 调度边界：`selected_agents` 负责表达“本轮真正执行谁”；系统只负责按 `allowed_analysis_agents / max_parallel_agents` 做合法性和预算裁剪，不再预设固定专家池。

## 2. 分析专家 Agent

- `LogAgent`: 基于 `api_endpoints / trace_ids / error_keywords` 重建日志时间线、异常模式和错误链路。
  - 深度重点：统一时序对齐、重试链路、超时传播、连接池耗尽与锁等待的时间因果关系。
- `DomainAgent`: 基于 `api_endpoints / domain / aggregate / dependency_services` 输出责任田归属、业务链路和上下游责任边界。
  - 深度重点：聚合约束、事务顺序、下游依赖补偿策略、责任边界冲突检查。
- `CodeAgent`: 基于 `class_names / code_artifacts / api_endpoints / service_names` 搜索代码仓，定位入口类、服务类、热点实现和回归风险。
  - 深度重点：代码闭包、事务边界、连接池配置、疑似问题代码片段与回归面。
- `DatabaseAgent`: 基于 `database_tables / api_endpoints / error_keywords` 读取表 Meta、索引、慢 SQL、Top SQL 和会话状态。
  - 深度重点：锁等待图、执行计划、SQL 模式聚类、热点表与连接池关联分析。
- `MetricsAgent`: 基于 `monitor_items / service_names / api_endpoints` 提取 CPU、线程、连接池、5xx 和异常窗口。
- `ImpactAnalysisAgent`: 基于 `api_endpoints / service_names / dependency_services / error_keywords / responsibility_mapping` 输出影响功能、影响接口和用户影响量化/估算。
  - 深度重点：功能级与接口级两层影响面、实测与估算口径区分、责任田与业务 blast radius 对齐。
- `ChangeAgent`: 基于 `service_names / code_artifacts / api_endpoints` 关联故障窗口前后的发布、提交和配置变化。
- `RunbookAgent`: 基于 `domain / aggregate / api_endpoints / error_keywords` 匹配相似案例和 SOP 处置建议。
- `RuleSuggestionAgent`: 告警规则与阈值优化建议。

分析阶段 Prompt 约束：
- 首轮分析专家默认采用 `independent-first` 模式，先基于自己的 `focused_context / tool_context` 独立取证，再参考同伴结论做补充或修正。
- `CriticAgent / RebuttalAgent / JudgeAgent / VerificationAgent` 继续采用 `peer-driven` 模式，以交叉验证、反驳和收敛为主。

## 3. 对抗与裁决 Agent

- `CriticAgent`: 识别证据缺口与逻辑漏洞。
- `RebuttalAgent`: 回应质疑并补充证据。
- `JudgeAgent`: 汇总多方观点，输出最终裁决。
  - 深度重点：收敛 Top-K 根因候选、证据覆盖率和 convergence score，避免只给单点结论。
- `VerificationAgent`: 输出验证计划与回归检查项。

## 4. 分析深度模式

- `quick`
  - 默认 1 轮，优先快速止血和高信号证据，不追求完整穷举。
  - 与 `standard` 共用同一批 `allowed_analysis_agents`，只是在 `max_parallel_agents / verification / critique / collaboration` 上更保守。
- `standard`
  - 默认 2 轮，适合常规排障，允许一轮追问和交叉校验。
  - 与 `quick` 的差异应主要体现在预算和容错，而不是预设不同的业务分发策略。
- `deep`
  - 默认 4 轮，适合复杂根因链路，要求更强的追问、证据覆盖和候选根因排序。
  - 运行策略会扩展到更宽的 analysis agent 集合、更高的 discussion budget，以及更宽松的分析 token/timeout 预算。

## 5. 新增 Agent 准入标准

1. 必须有单一职责，避免与现有 Agent 重叠。
2. 必须定义 phase、触发条件、输入输出 schema。
3. 必须定义工具门禁策略（可选工具、默认行为、失败回退）。
4. 必须新增至少一个 benchmark case。
5. 必须补充前端展示映射。
