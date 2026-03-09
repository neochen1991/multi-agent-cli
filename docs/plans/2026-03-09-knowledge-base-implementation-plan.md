# Knowledge Base Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 增加独立一级“知识库”模块，统一管理运维案例、Runbook/SOP 和故障复盘模板，使用本地 markdown 存储。

**Architecture:** 新增 `knowledge` 领域模型、repository、service、API 和前端页面；不引入数据库；沿用本地 markdown front matter 存储策略；前端在 legacy 导航中新增一级菜单。

**Tech Stack:** FastAPI, Pydantic, 本地 markdown 文件存储, React, Ant Design, Axios

---

### Task 1: Backend Knowledge Domain

**Files:**
- Create: `backend/app/models/knowledge.py`
- Modify: `backend/app/models/__init__.py`

**Steps**

1. 定义 `KnowledgeEntryType` 和 `KnowledgeEntry`。
2. 定义三类结构化字段模型：`CaseFields`、`RunbookFields`、`PostmortemTemplateFields`。
3. 导出模型供 repository/service/api 复用。

### Task 2: Backend Knowledge Repository

**Files:**
- Create: `backend/app/repositories/knowledge_repository.py`
- Modify: `backend/app/repositories/__init__.py`

**Steps**

1. 新建 markdown 存储目录初始化逻辑。
2. 实现 `save/get/list/delete/stats`。
3. 使用 front matter + markdown 正文格式落盘。

### Task 3: Backend Knowledge Service

**Files:**
- Create: `backend/app/services/knowledge_service.py`
- Modify: `backend/app/services/__init__.py`

**Steps**

1. 封装 CRUD 和筛选逻辑。
2. 支持按 `entry_type / q / tag` 过滤。
3. 首次启动自动注入少量示例知识条目。

### Task 4: Backend Knowledge API

**Files:**
- Create: `backend/app/api/knowledge.py`
- Modify: `backend/app/api/router.py`

**Steps**

1. 定义请求/响应 DTO。
2. 暴露 `list/get/create/update/delete/stats`。
3. 注册到 `/api/v1/knowledge`。

### Task 5: Frontend API Client

**Files:**
- Modify: `frontend/src/services/api.ts`

**Steps**

1. 定义 `KnowledgeEntry` 相关 TS 类型。
2. 新增 `knowledgeApi`。

### Task 6: Frontend Knowledge Page

**Files:**
- Create: `frontend/src/pages/Knowledge/index.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/common/Sider/index.tsx`
- Modify: `frontend/src/styles/global.css`

**Steps**

1. 新增一级菜单“知识库”。
2. 新增页面统计卡、Tabs、表格、详情抽屉。
3. 新增创建/编辑 Modal 表单。
4. 增加空态、加载态和删除确认交互。

### Task 7: Tests and Verification

**Files:**
- Create: `backend/tests/test_knowledge_service.py`

**Steps**

1. 为 service/repository 写 CRUD + stats 测试。
2. 运行后端测试。
3. 运行前端构建。

