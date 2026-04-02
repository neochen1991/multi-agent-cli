# SQLite Storage Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前项目的主要文件型结构化持久化统一迁移到 SQLite，并停止新写入旧 `json/jsonl` 文件。

**Architecture:** 新增统一 SQLite 基础设施，先替换 `incident/debate/report` 仓储，再替换 `runtime session/events/worklog/lineage/governance` 的文件读写。保留 `memory` 模式用于测试，不导入旧文件数据，不做双写。

**Tech Stack:** Python, sqlite3, FastAPI, Pydantic, pytest

---

### Task 1: 建立 SQLite 基础设施

**Files:**
- Create: `backend/app/storage/sqlite_store.py`
- Create: `backend/app/storage/__init__.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_sqlite_store.py`

**Step 1: 写失败测试**

覆盖：
- 首次初始化自动建库建表
- JSON payload 可写入与读出
- 同一路径复用数据库实例时不会丢表

**Step 2: 运行测试确认失败**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_sqlite_store.py -q`

**Step 3: 实现最小基础设施**

实现内容：
- 统一 SQLite 文件路径解析
- 建表入口
- 基础 `execute/fetchone/fetchall`
- JSON 序列化/反序列化帮助函数
- 关键代码加中文注释

**Step 4: 运行测试确认通过**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_sqlite_store.py -q`

### Task 2: 替换 IncidentRepository

**Files:**
- Modify: `backend/app/repositories/incident_repository.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_incident_repository.py`

**Step 1: 写失败测试**

覆盖：
- create/get/update/delete/list_all
- `LOCAL_STORE_BACKEND=sqlite` 时默认使用 SQLite 仓储

**Step 2: 跑失败测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_incident_repository.py -q`

**Step 3: 实现 SQLite 仓储**

实现内容：
- 新增 `SqliteIncidentRepository`
- 保持接口与 `FileIncidentRepository` 一致
- 服务层默认从 `file` 切换到 `sqlite`

**Step 4: 跑测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_incident_repository.py -q`

### Task 3: 替换 DebateRepository

**Files:**
- Modify: `backend/app/repositories/debate_repository.py`
- Modify: `backend/app/services/debate_service.py`
- Test: `backend/tests/test_debate_repository.py`

**Step 1: 写失败测试**

覆盖：
- save/get/list session
- save/get result
- session/result 分表存储正确

**Step 2: 跑失败测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_debate_repository.py -q`

**Step 3: 实现 SQLite 仓储**

实现内容：
- 新增 `SqliteDebateRepository`
- 会话与结果分表
- 保留内存实现供测试使用

**Step 4: 跑测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_debate_repository.py -q`

### Task 4: 替换 ReportRepository

**Files:**
- Modify: `backend/app/repositories/report_repository.py`
- Modify: `backend/app/services/report_service.py`
- Test: `backend/tests/test_report_repository.py`

**Step 1: 写失败测试**

覆盖：
- `save/get_latest/get_latest_by_format/list_by_incident`
- share token 存取

**Step 2: 跑失败测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_report_repository.py -q`

**Step 3: 实现 SQLite 仓储**

实现内容：
- 新增 `SqliteReportRepository`
- `reports` 与 `share_tokens` 分表
- 查询使用 `created_at DESC`

**Step 4: 跑测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_report_repository.py -q`

### Task 5: 替换 RuntimeSessionStore

**Files:**
- Modify: `backend/app/runtime/session_store.py`
- Test: `backend/tests/test_runtime_session_store.py`

**Step 1: 写失败测试**

覆盖：
- create/load
- append_round
- complete/mark_waiting_review/fail
- append_event

**Step 2: 跑失败测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_runtime_session_store.py -q`

**Step 3: 改为 SQLite**

实现内容：
- `runtime_sessions` 表替代 `runtime/sessions/*.json`
- `runtime_events` 表替代 `runtime/events/*.jsonl`
- 事件按自增 id 读取
- 保留现有方法签名

**Step 4: 跑测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_runtime_session_store.py -q`

### Task 6: 替换 WorkLogManager 与 Trace Lineage

**Files:**
- Modify: `backend/app/runtime/langgraph/work_log_manager.py`
- Modify: `backend/app/runtime/trace_lineage/recorder.py`
- Modify: `backend/app/runtime/trace_lineage/__init__.py`
- Test: `backend/tests/test_work_log_manager.py`
- Test: `backend/tests/test_trace_lineage.py`

**Step 1: 写失败测试**

覆盖：
- work log 从 SQLite 事件表构建上下文
- lineage 记录与回放

**Step 2: 跑失败测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_work_log_manager.py backend/tests/test_trace_lineage.py -q`

**Step 3: 实现替换**

实现内容：
- `WorkLogManager` 不再读 `jsonl`
- `lineage` 记录改写 `lineage_events`
- 回放按时间或自增 id 排序

**Step 4: 跑测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_work_log_manager.py backend/tests/test_trace_lineage.py -q`

### Task 7: 替换治理与辅助文件读写

**Files:**
- Modify: `backend/app/services/governance_ops_service.py`
- Modify: `backend/app/services/feedback_service.py`
- Modify: `backend/app/services/remediation_service.py`
- Test: `backend/tests/test_governance_ops_service.py`
- Test: `backend/tests/test_feedback_service.py`
- Test: `backend/tests/test_remediation_service.py`

**Step 1: 写失败测试**

覆盖：
- 治理统计不再读取 `debates.json`
- feedback/remediation 改为 SQLite

**Step 2: 跑失败测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_governance_ops_service.py backend/tests/test_feedback_service.py backend/tests/test_remediation_service.py -q`

**Step 3: 实现替换**

实现内容：
- 治理统计改查 SQLite 会话与事件表
- feedback/remediation 从文件改库表

**Step 4: 跑测试**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_governance_ops_service.py backend/tests/test_feedback_service.py backend/tests/test_remediation_service.py -q`

### Task 8: 全链路回归

**Files:**
- Modify: `README.md`
- Modify: `docs/wiki/code_wiki.md`
- Modify: `docs/agents/checkpoint-resume.md`
- Test: `backend/tests/test_debate_service_effective_conclusion.py`
- Test: `backend/tests/test_runtime_message_flow.py`
- Test: `backend/tests/test_smoke_scenarios.py`

**Step 1: 跑核心回归**

Run: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_runtime_message_flow.py backend/tests/test_debate_service_effective_conclusion.py backend/tests/test_smoke_scenarios.py -q`

**Step 2: 跑前端类型检查**

Run: `npm --prefix frontend run typecheck`

**Step 3: 跑 smoke**

Run:
- `SMOKE_SCENARIO=impact-scope-order-create node ./scripts/smoke-e2e.mjs`
- `SMOKE_SCENARIO=impact-scope-order-create SMOKE_MODE=standard node ./scripts/smoke-e2e.mjs`

**Step 4: 更新文档**

文档需明确：
- 结构化持久化唯一事实源已变为 SQLite
- 旧文件不自动导入
- `LOCAL_STORE_BACKEND` 推荐值为 `sqlite`

**Step 5: 收尾检查**

确认：
- 没有主路径继续写 `debates.json/reports.json/incidents.json/runtime/*.json*`
- 关键新增代码均带中文注释
