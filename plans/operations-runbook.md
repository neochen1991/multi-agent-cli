# 运行手册（部署 / 回滚 / 压测 / SLO）

## 启动
1. 后端
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
2. 前端
```bash
cd frontend
npm run dev
```

## 关键配置
- `LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/coding`
- `LLM_API_KEY=7b446c97-7172-4c90-a4ef-3f3ff5a8f894`
- `LLM_MODEL=kimi-k2.5`
- `LOCAL_STORE_BACKEND=file`（默认）
- `LOCAL_STORE_DIR=/tmp/sre_debate_store`
- `AUTH_ENABLED=false`（默认关闭；上线可设为 `true`）
- `RATE_LIMIT_REQUESTS_PER_MINUTE=120`

## 健康检查与指标
- 健康：`GET /health`
- 指标：`GET /metrics`
- WebSocket：`/ws/debates/{session_id}`

`/metrics` 中重点关注 `debate_slo`：
- `success_rate`：辩论成功率
- `p95_latency_ms`：辩论 P95 耗时
- `timeout_rate`：模型超时占比
- `retry_rate`：触发重试占比
- `invalid_conclusion_rate`：无效结论拦截占比

## SLO 建议阈值
- 成功率 `>= 95%`
- P95 耗时 `<= 180000ms`
- 超时率 `<= 10%`
- 重试率 `<= 20%`
- 无效结论率 `<= 2%`

## 回滚策略
1. 回滚应用版本到上一稳定 commit/tag。
2. 恢复环境变量（尤其是模型配置、鉴权开关、工具开关）。
3. 重启后端与前端服务。
4. 验证 `health`、核心 API、前端主流程与 `/metrics` 指标。

## 工具链配置排障
- `CodeAgent/ChangeAgent`：检查 `/api/v1/settings/tooling` 中 `code_repo.enabled/repo_url/token`。
- `LogAgent`：检查 `log_file.enabled/file_path`。
- `DomainAgent`：检查 `domain_excel.enabled/excel_path`。
- `MetricsAgent/RunbookAgent`：按主Agent命令触发，查看事件流中的 `agent_tool_context_prepared` 与 `agent_tool_io`。

## 故障回放样本
- 样本目录：`backend/tests/fixtures/incidents`（20+）
- 每个样本包含：症状、日志、堆栈、预期根因、预期责任田。
- 回放入口：`scripts/smoke-e2e.mjs`（支持多场景执行并输出通过率）。

## 压测（简易脚本）
```bash
cd backend
python tests/load/smoke_load_test.py --base-url http://localhost:8000 --requests 200 --concurrency 20
```

## 常见告警处置
1. `timeout_rate` 突增：检查 LLM 网关 RT、降低每轮并发 Agent 数、缩短上下文。
2. `invalid_conclusion_rate` 升高：检查 prompt 结构约束、验证是否存在 JSON 输出污染。
3. `retry_rate` 升高：检查工具链外部依赖（Git/日志文件/责任田文档）可用性。
