# Knowledge Base Module Design

**Goal**

新增独立一级“知识库”模块，用本地 markdown 文档存储统一管理三类知识条目：
- 运维案例
- Runbook / SOP
- 故障复盘模板

该模块面向人工维护与后续 Agent 检索复用，不引入外部数据库。

**Why**

当前项目已有“案例库”底层能力，但分散在资产服务内部：
- 没有独立一级入口
- 仅覆盖 case，不覆盖 SOP / 复盘模板
- 缺少统一的增删改查页面
- 缺少知识条目统计、筛选和详情管理体验

**Constraints**

- 存储方式必须保持本地文件优先，便于人工查看和版本管理
- 不引入外部数据库
- 尽量复用现有 `asset_repository` 的 markdown front matter 持久化方式
- 前端遵循现有 legacy 页面体系，保留原版为默认入口

## 1. Information Architecture

侧边栏新增一级菜单：`知识库`

页面结构：
- 顶部统计卡：总条目、案例数、Runbook 数、模板数
- 主内容区 Tabs：
  - 运维案例
  - Runbook / SOP
  - 复盘模板
- 每个 Tab 支持：
  - 搜索
  - 标签筛选
  - 新建
  - 编辑
  - 删除
  - 查看详情

详情展示遵循“结构化优先，Markdown 正文兜底”：
- 基础信息
- 标签/关联服务/领域聚合根
- 结构化字段
- Markdown 内容

## 2. Data Model

新增统一知识条目模型 `KnowledgeEntry`。

核心字段：
- `id`
- `entry_type`: `case | runbook | postmortem_template`
- `title`
- `summary`
- `content`
- `tags`
- `service_names`
- `domain`
- `aggregate`
- `author`
- `created_at`
- `updated_at`
- `metadata`

结构化字段按类型分组存入：
- `case_fields`
  - `incident_type`
  - `symptoms`
  - `root_cause`
  - `solution`
  - `fix_steps`
- `runbook_fields`
  - `applicable_scenarios`
  - `prechecks`
  - `steps`
  - `rollback_plan`
  - `verification_steps`
- `postmortem_fields`
  - `impact_scope_template`
  - `timeline_template`
  - `five_whys_template`
  - `action_items_template`

## 3. Storage

本地目录：
- `local_store/knowledge/cases/*.md`
- `local_store/knowledge/runbooks/*.md`
- `local_store/knowledge/postmortems/*.md`

文件格式：
- front matter 存结构化 JSON
- markdown 正文存 `content`

这样可以：
- 人工直接打开编辑
- 后续接入 git 管理
- 兼容当前案例库存储方式

## 4. Backend Architecture

新增模块：
- `backend/app/models/knowledge.py`
- `backend/app/repositories/knowledge_repository.py`
- `backend/app/services/knowledge_service.py`
- `backend/app/api/knowledge.py`

API：
- `GET /knowledge/entries`
- `GET /knowledge/entries/{entry_id}`
- `POST /knowledge/entries`
- `PUT /knowledge/entries/{entry_id}`
- `DELETE /knowledge/entries/{entry_id}`
- `GET /knowledge/stats`

关键设计：
- Repository 负责文件落盘和读取
- Service 负责筛选、搜索、默认示例、结构转换
- API 负责前后端 DTO

## 5. Frontend Architecture

新增页面：
- `frontend/src/pages/Knowledge/index.tsx`

新增 API client：
- `frontend/src/services/api.ts`

新增一级菜单：
- `frontend/src/components/common/Sider/index.tsx`

新增路由：
- `frontend/src/App.tsx`

交互策略：
- 列表 + 右侧抽屉详情
- 新建/编辑用 Modal + Form
- 每个类型共享统一表单骨架，按条目类型动态显示字段

## 6. Migration / Compatibility

不删除现有 `CaseLibrary` 能力，先保持兼容：
- 旧案例能力继续可被资产服务内部使用
- 新知识库模块独立实现，不直接破坏既有资产 API

后续如果需要，可再把 `RunbookAgent` 切换为直接读取新知识库 API。

## 7. Validation

至少验证：
- 后端 repository/service 的 CRUD
- API 的基本列表和更新流程
- 前端构建通过
- 页面可创建、编辑、删除、查看知识条目

## 8. Out of Scope

本轮不做：
- 外部数据库
- 向量检索
- 权限分级
- 富文本编辑器
- 和主分析链路深度联动

