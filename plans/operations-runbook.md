# 运行手册（部署 / 回滚 / 压测）

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
- `LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/v1`
- `LLM_API_KEY=sk-sp-5abc4c1d85414988979e90771e112f2f`
- `LLM_MODEL=glm-5`
- `LOCAL_STORE_BACKEND=file`（默认）
- `LOCAL_STORE_DIR=/tmp/sre_debate_store`
- `AUTH_ENABLED=false`（默认关闭；上线可设为 `true`）
- `RATE_LIMIT_REQUESTS_PER_MINUTE=120`

## 健康检查与指标
- 健康：`GET /health`
- 指标：`GET /metrics`
- WebSocket：`/ws/debates/{session_id}`

## 回滚策略
1. 回滚应用版本到上一稳定 commit/tag
2. 恢复环境变量（尤其是模型与鉴权开关）
3. 重启后端与前端服务
4. 验证 `health`、核心 API、前端主流程

## 本地仓储维护
```bash
npm run store:migrate
npm run store:clean
```

## 压测（简易脚本）
```bash
cd backend
python tests/load/smoke_load_test.py --base-url http://localhost:8000 --requests 200 --concurrency 20
```

## 故障演练建议
- 演练 401/403（`AUTH_ENABLED=true`）
- 演练 429（压高并发触发限流）
- 演练 LLM 网关不可用（观察熔断行为）
