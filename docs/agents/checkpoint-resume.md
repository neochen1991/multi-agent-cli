# Checkpoint And Resume

本文档补充运行时断点续写能力，作为 `/Users/neochen/multi-agent-cli_v2/AGENTS.md` 的展开说明。

## 1. 目标

- 会话异常中断后可以恢复，而不是重新开始整轮分析。
- 人工审核暂停后能从 `resume_from_step` 继续推进。
- 结构化状态恢复后，flat 字段只作为兼容视图重新镜像。

## 2. 关键状态

- `awaiting_human_review`
- `human_review_reason`
- `human_review_payload`
- `resume_from_step`
- `final_payload`
- `agent_local_state`

## 3. 当前实现入口

- runtime 状态定义：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/state.py`
- finalize 收口：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/services/finalization_service.py`
- review 边界：`/Users/neochen/multi-agent-cli_v2/backend/app/runtime/langgraph/services/review_boundary.py`
- DebateService checkpoint：`/Users/neochen/multi-agent-cli_v2/backend/app/services/debate_service.py`

## 4. 边界约束

- `session.context.human_review` 和 `final_payload.human_review` 应复用同一结构。
- `resume_from_step` 缺失时默认回到 `report_generation`。
- 任何人工审核暂停都必须写入可恢复的中间快照。
