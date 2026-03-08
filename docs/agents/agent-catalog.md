# Agent Catalog

## 1. 主控 Agent

- `ProblemAnalysisAgent`
  - phase: `coordination`
  - 职责：拆解问题、分发命令、推进讨论、触发收敛。
  - 分发原则：主 Agent 只给高层任务方向；系统会把责任田映射出的 `api_endpoints / code_artifacts / class_names / database_tables / monitor_items / dependency_services / trace_ids / error_keywords` 自动注入到各子 Agent 的命令与工具上下文。
  - 关键输出：`commands`、`next_step`、`should_stop`、`stop_reason`。

## 2. 分析专家 Agent

- `LogAgent`: 基于 `api_endpoints / trace_ids / error_keywords` 重建日志时间线、异常模式和错误链路。
- `DomainAgent`: 基于 `api_endpoints / domain / aggregate / dependency_services` 输出责任田归属、业务链路和上下游责任边界。
- `CodeAgent`: 基于 `class_names / code_artifacts / api_endpoints / service_names` 搜索代码仓，定位入口类、服务类、热点实现和回归风险。
- `DatabaseAgent`: 基于 `database_tables / api_endpoints / error_keywords` 读取表 Meta、索引、慢 SQL、Top SQL 和会话状态。
- `MetricsAgent`: 基于 `monitor_items / service_names / api_endpoints` 提取 CPU、线程、连接池、5xx 和异常窗口。
- `ChangeAgent`: 基于 `service_names / code_artifacts / api_endpoints` 关联故障窗口前后的发布、提交和配置变化。
- `RunbookAgent`: 基于 `domain / aggregate / api_endpoints / error_keywords` 匹配相似案例和 SOP 处置建议。
- `RuleSuggestionAgent`: 告警规则与阈值优化建议。

## 3. 对抗与裁决 Agent

- `CriticAgent`: 识别证据缺口与逻辑漏洞。
- `RebuttalAgent`: 回应质疑并补充证据。
- `JudgeAgent`: 汇总多方观点，输出最终裁决。
- `VerificationAgent`: 输出验证计划与回归检查项。

## 4. 新增 Agent 准入标准

1. 必须有单一职责，避免与现有 Agent 重叠。
2. 必须定义 phase、触发条件、输入输出 schema。
3. 必须定义工具门禁策略（可选工具、默认行为、失败回退）。
4. 必须新增至少一个 benchmark case。
5. 必须补充前端展示映射。
