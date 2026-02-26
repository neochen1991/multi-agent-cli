# SRE Debate Platform - 多模型辩论式 SRE 智能体平台

基于 AutoGen 多 Agent 编排构建的多模型辩论式 SRE 智能体平台，实现三态资产融合与 AI 技术委员会决策系统。

## 🚀 核心特性

- **🔥 三态资产融合**：统一建模运行态、开发态、设计态资产
- **🧠 专家委员会协作**：统一使用 glm-5 模型执行多角色协作分析
- **⚖️ AI 内部辩论机制**：通过质疑、反驳、裁决四阶段辩论流程
- **🔗 可扩展自动修复能力**：支持自动 PR 生成与灰度发布建议

## 📋 系统架构

```
┌────────────────────────────────────┐
│           交互与接口层             │
│  Web UI / API / 日志上传 / 结果展示 │
└────────────────────────────────────┘
                    ↓
┌────────────────────────────────────┐
│          Flow 编排层               │
│    SRE Debate Flow (AutoGen)      │
└────────────────────────────────────┘
                    ↓
┌────────────────────────────────────┐
│        多模型专家协作层            │
│ Code | Design | Critic | Judge     │
└────────────────────────────────────┘
                    ↓
┌────────────────────────────────────┐
│     AutoGen Agent Orchestration   │
│   Multi-agent multi-round debate  │
└────────────────────────────────────┘
```

## 🛠️ 技术栈

### 后端
- Python 3.11+
- FastAPI
- AutoGen (pyautogen)
- 本地文件仓储（默认）/ 内存仓储（可选）
- Redis + Celery（可选）

### 前端
- React 18
- TypeScript
- Ant Design 5
- Vite

### 已实现能力（可运行）
- Incident 全流程（创建 -> 会话 -> 辩论 -> 报告）
- WebSocket 实时辩论流（`/ws/debates/{session_id}`）
- 资产融合查询（`/api/v1/assets/fusion/{incident_id}`）
- 历史记录与资产图谱页面
- 可选鉴权（JWT/RBAC，`AUTH_ENABLED=true`）
- 限流、熔断、指标端点（`/metrics`）

## 📁 项目结构

```
multi-agent-cli_v2/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── api/               # API 路由
│   │   ├── agents/            # Agent 实现
│   │   ├── flows/             # Flow 编排
│   │   ├── tools/             # 工具实现
│   │   ├── models/            # 数据模型
│   │   ├── services/          # 业务服务
│   │   └── core/              # 核心组件
│   └── tests/                 # 测试
│
├── frontend/                   # React 前端
│   └── src/
│       ├── components/        # 组件
│       ├── pages/             # 页面
│       ├── stores/            # 状态管理
│       └── hooks/             # 自定义 Hooks
│
├── docker/                     # Docker 配置
│   ├── docker-compose.yml
│   ├── Dockerfile.backend
│   └── Dockerfile.frontend
│
└── plans/                      # 规划文档
    ├── sre-debate-platform-architecture.md
    ├── implementation-roadmap.md
    └── project-structure.md
```

## 🤖 多模型专家分工

| Agent | 模型 | 角色 |
|-------|------|------|
| LogAgent | glm-5 | 日志分析专家 |
| DomainAgent | glm-5 | 领域映射专家 |
| CodeAgent | glm-5 | 代码分析专家 |
| CriticAgent | glm-5 | 架构质疑专家 |
| RebuttalAgent | glm-5 | 技术反驳专家 |
| JudgeAgent | glm-5 | 技术委员会主席 |

## 🔄 辩论流程

1. **独立分析** - CodeAgent 提出根因假设
2. **交叉质疑** - CriticAgent 检查 DDD 原则违反
3. **反驳修正** - RebuttalAgent 回应质疑
4. **最终裁决** - JudgeAgent 综合裁决

## 🚀 快速开始

### 前置要求

1. **安装 Python 依赖（含 AutoGen）**

   ```bash
   pip install -r requirements.txt
   ```

2. **配置模型提供商**

通过环境变量配置 OpenAI 兼容网关：
- `LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/v1`
- `LLM_API_KEY=sk-sp-5abc4c1d85414988979e90771e112f2f`
- `LLM_MODEL=glm-5`
- `LOCAL_STORE_BACKEND=file`
- `LOCAL_STORE_DIR=/tmp/sre_debate_store`

### 环境要求
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (可选)

### 后端启动

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
export LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
export LLM_API_KEY=sk-sp-5abc4c1d85414988979e90771e112f2f
export LLM_MODEL=glm-5
export LOCAL_STORE_BACKEND=file

# 启动服务
uvicorn app.main:app --reload
```

对应系统 LLM 配置结构：

```json
{
  "options": {
    "baseURL": "https://coding.dashscope.aliyuncs.com/v1",
    "apiKey": "sk-sp-5abc4c1d85414988979e90771e112f2f"
  },
  "models": {
    "glm-5": {
      "name": "glm-5"
    }
  }
}
```

### 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 一键启动（Backend + Frontend）

在项目根目录执行：

```bash
npm run start:all
```

说明：
- 会一次性启动后端 `uvicorn`、前端 `vite`
- 日志输出目录：`.run/logs/`
- 按 `Ctrl+C` 可停止全部服务

常用停止命令：

```bash
# 按 PID 文件停止
npm run stop:all

# 如果有端口残留占用，强制清理 8000/5173
npm run stop:all:force
```

本地仓储维护命令：

```bash
# 迁移历史仓储文件，补齐 schema_version
npm run store:migrate

# 清理本地仓储临时文件与备份文件
npm run store:clean
```

### Docker 部署

```bash
# 启动所有服务
docker-compose -f docker/docker-compose.yml up -d
```

## 📚 API 文档

启动后端服务后，访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Metrics: http://localhost:8000/metrics

## 🗂️ 资产示例（领域-聚合根）

新增本地 Markdown 资产样例（目录：`backend/examples/assets`）：
- `domain-aggregate-design.md`：领域-聚合根详细设计方案
- `domain-aggregate-responsibility.md`：领域-聚合根责任田清单（接口/代码/数据库表）
- `operations-case-library.md`：运维案例库

新增接口定位能力：

```bash
curl -X POST http://localhost:8000/api/v1/assets/locate \\
  -H 'Content-Type: application/json' \\
  -d '{
    "log_content": "ERROR POST /api/v1/orders failed with NullPointerException",
    "symptom": "下单失败"
  }'
```

返回将包含：
- 命中的领域与聚合根
- 对应接口、代码清单、数据库表清单
- 详细设计引用与聚合根设计要点
- 相似运维案例

## 🔧 AutoGen 调用说明

本项目通过 AutoGen 组织多 Agent 多轮对话调用大模型。

### 核心工作流程

```python
from app.core.autogen_client import AutoGenClient

# 创建客户端
client = AutoGenClient()

# 创建会话
session = await client.create_session(title="故障分析会话")

# 发送提示消息
result = await client.send_prompt(
    session_id=session.id,
    parts=[{"type": "text", "text": "分析这个日志..."}],
    model={"name": "glm-5"}
)

# 获取结构化输出
result = await client.send_structured_prompt(
    session_id=session.id,
    text="分析日志并输出 JSON 格式结果",
    schema={
        "type": "object",
        "properties": {
            "root_cause": {"type": "string"},
            "confidence": {"type": "number"}
        }
    }
)
```

### 可用的 API

| API | 说明 |
|-----|------|
| `create_session()` | 创建会话 |
| `send_prompt()` | 发送提示消息 |
| `send_structured_prompt()` | 发送结构化输出提示 |
| `get_messages()` | 获取消息列表 |
| `list_agents()` | 列出可用 Agent |
| `get_providers()` | 获取模型提供商 |

## 🔐 鉴权（可选）

默认关闭鉴权：`AUTH_ENABLED=false`。  
如需开启：

```bash
export AUTH_ENABLED=true
```

默认测试账号：
- `admin / admin123`
- `analyst / analyst123`
- `viewer / viewer123`

## 📖 详细文档

- [技术架构方案](plans/sre-debate-platform-architecture.md)
- [实施路线图](plans/implementation-roadmap.md)
- [项目目录结构](plans/project-structure.md)
- [测试矩阵](plans/test-matrix.md)
- [运行手册](plans/operations-runbook.md)
- [AutoGen 文档](https://microsoft.github.io/autogen/)

## 📝 开发状态

### 已完成
- [x] 项目架构设计
- [x] 后端核心框架
- [x] AutoGen 多 Agent 调用集成
- [x] Agent 基类和各专家 Agent
- [x] 辩论流程编排
- [x] 工具层实现
- [x] API 路由
- [x] 前端基础框架
- [x] Docker 配置

### 待完成
- [ ] 数据库持久化
- [ ] WebSocket 实时通信
- [ ] 案例库集成
- [ ] 测试覆盖
- [ ] 生产环境部署

## 📄 License

MIT License
