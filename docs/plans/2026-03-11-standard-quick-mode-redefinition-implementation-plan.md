# Standard / Quick 模式重定义实施计划

## Task 1: 重构 Runtime Policy

目标：

- 把 `standard` 定义为完整分析策略
- 把 `quick` 定义为弱模型友好策略
- 让 `background` 不再决定分析能力等级

改动文件：

- `backend/app/runtime/langgraph/runtime_policy.py`

验收：

- `standard` 与 `quick` 的 agent 集、discussion steps、协作能力有明确差异

## Task 2: 重构 Budgeting / Timeout / Queue

目标：

- `quick` 明显降低 LLM 压力
- `standard` 保留深度分析预算

改动文件：

- `backend/app/runtime/langgraph/budgeting.py`
- `backend/app/runtime/langgraph_runtime.py`

验收：

- `quick` 的 prompt 压缩、token、timeout、queue 预算明显偏保守
- `standard` 不再被错误压成“快而浅”

## Task 3: 调整前端文案

目标：

- 用户能够理解 `standard / quick / background`

改动文件：

- `frontend/src/components/incident/IncidentOverviewPanel.tsx`
- `frontend/src/pages/Home/index.tsx`
- `frontend/src/v2/pages/HomeV2.tsx`
- `frontend/src/v2/pages/IncidentV2.tsx`

验收：

- 不再把 `quick` 描述成单纯“快速”
- 明确指出 `standard` 适合强模型、`quick` 适合弱模型

## Task 4: 补策略回归测试

目标：

- 固化 `standard / quick` 的行为差异

改动文件：

- `backend/tests/runtime/test_depth_policy_modes.py`
- `backend/tests/test_runtime_message_flow.py`
- 需要时补新的 mode policy 测试文件

验收：

- `quick` 与 `standard` 的专家集、讨论步数、验证要求、预算均可测试

## 执行顺序

1. Task 1
2. Task 2
3. Task 3
4. Task 4

## 验证命令

```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/runtime/test_depth_policy_modes.py
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py -k "quick or standard or budget or round_evaluate"
npm --prefix frontend run typecheck
npm --prefix frontend run build
```
