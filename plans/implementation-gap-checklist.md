# 多模型 SRE 平台缺口补齐计划清单

## 目标
- 补齐现有实现与方案之间的核心能力差距
- 从“可运行骨架”推进到“可落地可运维系统”

## P0（本周必须完成）
- [x] 修复 `debates` 调用 `incident_service.update_incident()` 的类型不匹配问题
- [x] 打通报告 API：实现 `GET /reports/{incident_id}`、`export`、`regenerate`、`share`
- [x] 抽离内存存储为仓储接口（Incident / Debate / Asset）
- [ ] 引入 PostgreSQL 最小可用持久化（Incidents、Debates、DebateRounds、Reports）- 暂缓（当前要求：不引入外部数据库）
- [ ] 增加数据库迁移（Alembic）并落第一版 schema - 暂缓（当前要求：不引入外部数据库）
- [x] 为关键接口补基础测试（incident/debate/report 主流程）

## P1（两周内）
- [x] 实现 WebSocket 实时辩论流：`/ws/debates/{id}`
- [x] 实现辩论轮次控制（`max_rounds`）与共识检测（`consensus_threshold`）
- [x] 实现 Context Manager（对话上下文、资产上下文、轮次上下文）
- [x] 完成工具层缺口：`git_tool.py`、`ddd_analyzer.py`、`db_tool.py`、`case_library.py`
- [x] 将案例库从内存实现升级为可持久化 + 检索接口（本地 Markdown）
- [x] 前端接入真实 API（incidents/debates/reports/assets）
- [x] 前端实现辩论可视化组件（时间线、轮次、置信度、结论）

## P2（一个月内）
- [x] 接入 Redis（缓存、会话上下文）与 Celery（异步辩论/报告任务）- 可选模式（默认本地运行）
- [x] 完成资产融合结果查询接口（如 `/assets/fusion/{incidentId}`）
- [x] 完成资产图谱页面（含运行态/开发态/设计态关联视图）
- [x] 建立测试矩阵：单元测试、集成测试、端到端测试
- [x] 建立 CI 流水线：lint、typecheck、test、build
- [x] 增加观测：结构化日志、核心指标、错误告警

## P3（发布前）
- [x] 增加鉴权与权限控制（JWT / RBAC）- 可选开关（`AUTH_ENABLED`）
- [x] 增加 API 限流与熔断策略
- [x] 安全扫描与依赖漏洞治理（CI 审计步骤）
- [x] 压测与容量评估（并发、延迟、稳定性）- 提供轻量压测脚本
- [x] 完成部署文档与运行手册（回滚、故障演练）

## 里程碑验收
- [x] 功能：日志上传、三态资产融合、辩论流程、报告生成、实时可视化全部可用
- [ ] 性能：核心 API P95 < 500ms，单次辩论流程 < 5 分钟（第 2 项暂缓，先保证功能可用）
- [ ] 质量：单测覆盖率 > 80%，无高危漏洞，CI 全绿
