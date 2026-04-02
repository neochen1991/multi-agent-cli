# SQLite Storage Unification Design

**背景**

当前项目仍有多处本地文件持久化：
- `incidents.json`
- `debates.json`
- `reports.json`
- `runtime/sessions/*.json`
- `runtime/events/*.jsonl`
- `lineage/*.jsonl`
- `feedback.json`
- `remediation_actions.json`

这会带来几个工程问题：
- 同一会话状态分散在多个文件和目录，治理统计与恢复逻辑需要跨源拼装。
- 文件追加写入和全量覆盖写入并存，难以保证一致性与查询效率。
- 历史记录、回放、断点恢复、治理接口无法共享统一查询模型。
- 后续要支持更复杂的筛选、分页、聚合统计时，文件存储会迅速成为瓶颈。

**目标**

将项目中当前主要文件持久化统一为 SQLite，形成单机部署下的唯一事实源。

本次迁移范围：
- `incident`
- `debate session`
- `debate result`
- `report`
- `runtime session`
- `runtime event`
- `lineage event`
- `feedback`
- `remediation action`
- `governance` 侧对上述数据的读取链路

明确不做：
- 不自动导入旧文件数据
- 不保留文件与 SQLite 双写
- 不替换资产目录、知识库目录、tool cache、导出文件等“文件本体”存储

**设计原则**

1. SQLite 成为结构化持久化唯一事实源。
2. 旧文件停止新写入，但不自动删除。
3. 运行时接口、服务层、前端接口尽量保持不变，优先做存储实现替换。
4. 新增关键代码必须加中文注释，说明表职责、兼容行为和失败处理。
5. 所有事件类数据保留按时间顺序回放能力。

**方案对比**

## 方案 A：仅替换业务仓储

只把 `IncidentRepository / DebateRepository / ReportRepository` 改成 SQLite，运行时事件和 lineage 继续保留文件。

优点：
- 改动小
- 回归风险低

缺点：
- 仍然存在双事实源
- 历史记录、回放、治理统计还要跨文件与数据库聚合
- 无法实现“全量文件存储改成 SQLite”的目标

## 方案 B：全量结构化持久化统一到 SQLite

将业务仓储、运行时状态、事件流、谱系、治理辅助数据统一落 SQLite。

优点：
- 结构清晰，单一事实源
- 查询、分页、聚合、治理和回放都更容易实现
- 后续扩展性更好

缺点：
- 涉及面较大
- 需要系统性回归验证

## 方案 C：双写过渡

SQLite 与旧文件同时写，稳定后再切换读取。

优点：
- 回滚最保守

缺点：
- 代码复杂度和维护成本高
- 双写失败、读写源不一致会引入新问题

**推荐**

采用方案 B，但执行策略上分层替换：
1. 先建立统一 SQLite 基础设施。
2. 再替换业务仓储。
3. 再替换 runtime session/events/worklog/lineage/governance。
4. 最后更新测试和文档。

**数据库文件与配置**

- 默认数据库文件：`{LOCAL_STORE_DIR}/app.db`
- 继续保留 `memory` 模式用于测试
- 原 `LOCAL_STORE_BACKEND=file` 迁移为 `sqlite`

建议新增配置：
- `LOCAL_STORE_BACKEND=sqlite|memory`
- `LOCAL_STORE_SQLITE_PATH`

**表设计**

## 1. incidents

存储故障基础信息。

核心字段：
- `id TEXT PRIMARY KEY`
- `payload_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

说明：
- 主体对象继续使用 Pydantic 模型，SQLite 先按整对象 JSON 存储，避免本次迁移变成表结构重构。
- 常用查询字段后续可按需拆列。

## 2. debate_sessions

存储会话对象。

核心字段：
- `id TEXT PRIMARY KEY`
- `incident_id TEXT NOT NULL`
- `status TEXT NOT NULL`
- `phase TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

## 3. debate_results

存储最终结果。

核心字段：
- `session_id TEXT PRIMARY KEY`
- `incident_id TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

## 4. reports

存储报告历史版本。

核心字段：
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `report_id TEXT`
- `incident_id TEXT NOT NULL`
- `format TEXT`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

索引：
- `(incident_id, created_at DESC)`
- `(incident_id, format, created_at DESC)`

## 5. share_tokens

存储分享 token 到 incident 的映射。

字段：
- `token TEXT PRIMARY KEY`
- `incident_id TEXT NOT NULL`
- `created_at TEXT NOT NULL`

## 6. runtime_sessions

存储断点恢复所需的运行态。

字段：
- `session_id TEXT PRIMARY KEY`
- `trace_id TEXT NOT NULL`
- `status TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

## 7. runtime_events

存储事件流，用于回放、worklog、治理和前端实时/历史展示。

字段：
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `session_id TEXT NOT NULL`
- `event_type TEXT`
- `agent_name TEXT`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

索引：
- `(session_id, id)`
- `(session_id, created_at)`

## 8. lineage_events

存储谱系记录。

字段：
- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `session_id TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

## 9. feedback_items

存储反馈数据。

字段：
- `id TEXT PRIMARY KEY`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

## 10. remediation_actions

存储修复动作数据。

字段：
- `id TEXT PRIMARY KEY`
- `created_at TEXT NOT NULL`
- `payload_json TEXT NOT NULL`

**实现策略**

## SQLite 基础设施

新增统一模块：
- `backend/app/storage/sqlite_store.py`

职责：
- 建库建表
- 提供连接与事务包装
- 统一 JSON 序列化/反序列化
- 提供线程安全锁

说明：
- 当前后端是异步应用，但仓储逻辑以轻量本地 I/O 为主，可先在异步方法内通过全局锁串行执行 SQLite 操作，控制复杂度。
- 如后续并发瓶颈明显，再引入更细粒度连接池或 `aiosqlite`。

## 仓储替换

为每个文件仓储新增 SQLite 实现：
- `SqliteIncidentRepository`
- `SqliteDebateRepository`
- `SqliteReportRepository`

接口保持不变，服务层不需要改业务协议。

## 运行时替换

重点替换以下文件读写：
- `backend/app/runtime/session_store.py`
- `backend/app/runtime/langgraph/work_log_manager.py`
- `backend/app/runtime/trace_lineage/recorder.py`
- `backend/app/services/governance_ops_service.py`

读取模式改为：
- 事件流从 `runtime_events` 查出，按 `id ASC` 或 `created_at ASC` 回放
- work log 从 `runtime_events` 聚合
- checkpoint/resume 从 `runtime_sessions` 读取
- lineage 从 `lineage_events` 读取

## 保留文件存储的边界

以下内容仍保留文件系统，不属于本次 SQLite 迁移：
- `assets/`
- `knowledge/`
- `tool_cache/`
- 导出的 markdown/html/pdf 等文件本体

原因：
- 这些是文件资源而不是结构化状态
- 强行存 SQLite 只会增加复杂度，不带来明显收益

**兼容行为**

1. 启动后只写 SQLite。
2. 不回读旧 `json/jsonl`。
3. 如果 SQLite 中不存在某条数据，则按“无记录”处理，不自动 fallback 到文件。
4. 文档里明确说明：旧文件仅作为历史遗留，不再参与运行。

**风险与缓解**

## 风险 1：历史页或治理页查不到旧数据

原因：
- 不导入旧文件。

缓解：
- 文档明确说明切换后只展示 SQLite 期内数据。

## 风险 2：事件顺序错乱影响回放

缓解：
- `runtime_events` 使用自增 `id`
- 回放时优先按 `id ASC`

## 风险 3：运行时事件写入变慢

缓解：
- 先保持单进程内锁保护
- 事件 payload 直接 JSON 存储，不做重 schema 化

## 风险 4：部分治理代码仍在读旧文件

缓解：
- 统一全局检索 `json/jsonl` 读路径并替换
- 为治理接口补专项回归测试

**验证策略**

1. 仓储测试
- incident/debate/report CRUD
- share token 映射

2. 运行时测试
- runtime session create/load/append_round/complete
- runtime event append/read/worklog build
- lineage record/replay

3. 服务/API 测试
- debate history
- debate result
- governance stats
- human review resume

4. 端到端 smoke
- 至少跑一轮 `quick`
- 至少跑一轮 `standard`
- 验证历史记录、结果页、回放链路无回归

**预期结果**

迁移完成后：
- 项目结构化状态统一保存在 SQLite
- 文件型状态仓储退出主路径
- 断点恢复、历史记录、回放、治理统计共享同一事实源
- 后续增加筛选、分页、聚合分析会更简单
