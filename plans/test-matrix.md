# 测试矩阵

## Unit
- `backend/tests/test_p0_incident_debate_report.py`
  - Incident 创建与状态更新
  - Debate 创建与执行链路
  - Report 生成/导出/分享
  - Assets 仓储与融合接口
  - Auth 开关与鉴权行为

## Integration
- FastAPI `TestClient` 真实路由级测试（同上文件）
- 前端构建集成验证：`cd frontend && npm run build`

## E2E (Manual)
1. 启动后端：`cd backend && uvicorn app.main:app --reload`
2. 启动前端：`cd frontend && npm run dev`
3. 打开 `http://localhost:5173`：
   - 创建 Incident
   - 启动实时辩论（WebSocket）
   - 查看报告与资产融合
   - 在 History 页面回看记录

## CI Gates
- Backend: `ruff` + `pytest`
- Frontend: `typecheck` + `build`
- Security: `pip-audit` + `npm audit`（非阻塞）

