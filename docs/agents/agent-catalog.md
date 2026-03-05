# Agent Catalog

## 1. 主控 Agent

- `ProblemAnalysisAgent`
  - phase: `coordination`
  - 职责：拆解问题、分发命令、推进讨论、触发收敛。
  - 关键输出：`commands`、`next_step`、`should_stop`、`stop_reason`。

## 2. 分析专家 Agent

- `LogAgent`: 日志时序、异常模式、错误链路。
- `DomainAgent`: 接口到领域/聚合根/责任田映射。
- `CodeAgent`: 代码路径、热点实现、回归风险。
- `DatabaseAgent`: 表结构、索引、慢 SQL、Top SQL、会话状态。
- `MetricsAgent`: CPU/线程/连接池/5xx 及波动窗口。
- `ChangeAgent`: 变更窗口关联与发布相关性。
- `RunbookAgent`: 案例库匹配与 SOP 处置建议。
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
