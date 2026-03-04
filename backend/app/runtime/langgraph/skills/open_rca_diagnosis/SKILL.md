# Open RCA Diagnosis Skill

## Stages
1. `context_intake`: 解析故障范围、接口、服务、影响面。
2. `evidence_collection`: 从日志/代码/领域/指标收集证据。
3. `cross_validation`: 跨 Agent 交叉验证，反驳与采纳并行。
4. `judgment`: 输出 Top-K 根因候选与置信度。
5. `verification`: 给出可执行验证与回滚路径。

## Rules
- 结论必须引用证据，且至少满足“日志或指标 + 代码或领域”的跨源约束。
- 主Agent命令优先级最高，子Agent必须先确认命令再执行。
- 输出要结构化并可审计，避免纯自然语言长段落。

## Forbidden
- 只给“需要进一步分析”且不提供下一步动作。
- 未引用证据直接给根因结论。
- 与主Agent命令无关的工具调用。

## Output Contract
- `chat_message`: 用户可读的会议发言（1-3句）。
- `analysis`: 分析过程摘要。
- `conclusion`: 当前阶段结论。
- `confidence`: 0~1。
- `evidence_chain`: 证据链数组（包含来源引用）。
