# 测试矩阵

## Unit
- `backend/tests/test_p0_incident_debate_report.py`
  - Incident 创建与状态更新
  - Debate 创建与执行链路
  - Report 生成/导出/分享
  - Assets 仓储与融合接口
  - Auth 开关与鉴权行为
- `backend/tests/test_state_transition_service.py`
  - messages 主通道与历史投影一致性
- `backend/tests/test_event_schema_stability.py`
  - 事件 `event_id` 稳定性
- `backend/tests/test_report_guard.py`
  - 无有效结论时报告门禁

## Integration
- FastAPI `TestClient` 真实路由级测试（同上文件）
- 前端构建集成验证：`cd frontend && npm run build`

## E2E
1. 本地服务启动
```bash
npm run start:all
```
2. 多场景回归（输出通过率与失败明细）
```bash
node ./scripts/smoke-e2e.mjs
```
3. 可选指定场景
```bash
SMOKE_SCENARIO=order-502-db-lock node ./scripts/smoke-e2e.mjs
SMOKE_SCENARIO=order-404-route-miss node ./scripts/smoke-e2e.mjs
SMOKE_SCENARIO=payment-timeout-upstream node ./scripts/smoke-e2e.mjs
```

## Fixtures（回放样本）
- 目录：`backend/tests/fixtures/incidents`
- 数量：20+
- 结构字段：`id/title/symptom/log_excerpt/stacktrace/expected_root_cause/expected_domain/expected_aggregate`

## CI Gates
- Backend: `ruff` + `pytest`
- Frontend: `typecheck` + `build`
- E2E Smoke: `node ./scripts/smoke-e2e.mjs`
- Security: `pip-audit` + `npm audit`（非阻塞）
