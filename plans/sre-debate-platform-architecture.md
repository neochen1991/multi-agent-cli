# 多模型辩论式 SRE 智能体平台 - 技术架构方案

## 1. 项目概述

### 1.1 项目目标
基于 AutoGen Runtime 构建多模型辩论式 SRE 智能体平台，实现：
- 三态资产（设计态/开发态/运行态）统一建模
- 多模型专家分工协作
- AI 内部质疑 + 反驳 + 仲裁机制
- 自动生成根因、修复方案与影响分析

### 1.2 技术栈
- **后端**: Python + FastAPI + AutoGen Runtime
- **前端**: React + TypeScript + Ant Design
- **数据库**: PostgreSQL + Neo4j (图数据库)
- **消息队列**: Redis + Celery
- **AI 模型**: glm-5

---

## 2. 系统架构设计

### 2.1 总体架构图

```mermaid
graph TB
    subgraph 交互层
        WebUI[Web UI - React]
        API[REST API]
        CLI[CLI Tool]
    end

    subgraph 网关层
        Gateway[API Gateway]
        Auth[认证授权]
        RateLimit[限流控制]
    end

    subgraph 编排层
        FlowEngine[Flow 编排引擎]
        DebateOrchestrator[辩论协调器]
        ContextManager[上下文管理器]
    end

    subgraph Agent层
        LogAgent[LogAgent - glm-5]
        DomainAgent[DomainAgent - glm-5]
        CodeAgent[CodeAgent - glm-5]
        CriticAgent[CriticAgent - glm-5]
        RebuttalAgent[RebuttalAgent - glm-5]
        JudgeAgent[JudgeAgent - glm-5]
    end

    subgraph 工具层
        LogParser[日志解析器]
        GitTool[Git 工具]
        DDDTool[DDD 分析工具]
        DBTool[数据库工具]
        CaseLib[案例库检索]
    end

    subgraph 资产层
        RuntimeAsset[运行态资产]
        DevAsset[开发态资产]
        DesignAsset[设计态资产]
    end

    subgraph 存储层
        PostgreSQL[(PostgreSQL)]
        Neo4j[(Neo4j)]
        Redis[(Redis)]
        VectorDB[(向量数据库)]
    end

    WebUI --> Gateway
    API --> Gateway
    CLI --> Gateway
    
    Gateway --> Auth
    Gateway --> RateLimit
    Gateway --> FlowEngine
    
    FlowEngine --> DebateOrchestrator
    DebateOrchestrator --> ContextManager
    
    DebateOrchestrator --> LogAgent
    DebateOrchestrator --> DomainAgent
    DebateOrchestrator --> CodeAgent
    DebateOrchestrator --> CriticAgent
    DebateOrchestrator --> RebuttalAgent
    DebateOrchestrator --> JudgeAgent
    
    LogAgent --> LogParser
    CodeAgent --> GitTool
    DomainAgent --> DDDTool
    CodeAgent --> DBTool
    DomainAgent --> CaseLib
    
    LogParser --> RuntimeAsset
    GitTool --> DevAsset
    DDDTool --> DesignAsset
    
    RuntimeAsset --> PostgreSQL
    DevAsset --> PostgreSQL
    DesignAsset --> PostgreSQL
    
    RuntimeAsset --> Neo4j
    DevAsset --> Neo4j
    DesignAsset --> Neo4j
    
    CaseLib --> VectorDB
    ContextManager --> Redis
```

### 2.2 核心模块划分

```
multi-agent-cli_v2/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置管理
│   │   ├── api/               # API 路由
│   │   │   ├── __init__.py
│   │   │   ├── incidents.py   # 故障事件 API
│   │   │   ├── assets.py      # 资产管理 API
│   │   │   ├── debates.py     # 辩论流程 API
│   │   │   └── reports.py     # 报告生成 API
│   │   ├── agents/            # Agent 实现
│   │   │   ├── __init__.py
│   │   │   ├── base.py        # Agent 基类
│   │   │   ├── log_agent.py   # 日志分析 Agent
│   │   │   ├── domain_agent.py# 领域映射 Agent
│   │   │   ├── code_agent.py  # 代码分析 Agent
│   │   │   ├── critic_agent.py# 质疑 Agent
│   │   │   ├── rebuttal_agent.py # 反驳 Agent
│   │   │   └── judge_agent.py # 裁决 Agent
│   │   ├── flows/             # Flow 编排
│   │   │   ├── __init__.py
│   │   │   ├── debate_flow.py # 辩论流程
│   │   │   └── context.py     # 上下文管理
│   │   ├── tools/             # 工具实现
│   │   │   ├── __init__.py
│   │   │   ├── log_parser.py  # 日志解析
│   │   │   ├── git_tool.py    # Git 操作
│   │   │   ├── ddd_analyzer.py# DDD 分析
│   │   │   └── db_tool.py     # 数据库操作
│   │   ├── models/            # 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── incident.py    # 故障模型
│   │   │   ├── asset.py       # 资产模型
│   │   │   └── report.py      # 报告模型
│   │   ├── services/          # 业务服务
│   │   │   ├── __init__.py
│   │   │   ├── asset_fusion.py# 资产融合
│   │   │   ├── case_library.py# 案例库
│   │   │   └── report_gen.py  # 报告生成
│   │   └── core/              # 核心组件
│   │       ├── __init__.py
│   │       ├── autogen_client.py # AutoGen Runtime 封装
│   │       └── model_router.py    # 模型路由
│   ├── tests/                 # 测试
│   ├── requirements.txt
│   └── pyproject.toml
│
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── components/        # 组件
│   │   │   ├── IncidentInput/ # 故障输入
│   │   │   ├── DebateViewer/  # 辩论可视化
│   │   │   ├── ReportView/    # 报告展示
│   │   │   └── AssetGraph/    # 资产图谱
│   │   ├── pages/             # 页面
│   │   │   ├── Home/          # 首页
│   │   │   ├── Incident/      # 故障分析
│   │   │   ├── Assets/        # 资产管理
│   │   │   └── History/       # 历史记录
│   │   ├── services/          # API 服务
│   │   ├── stores/            # 状态管理
│   │   ├── hooks/             # 自定义 Hooks
│   │   └── utils/             # 工具函数
│   ├── package.json
│   └── vite.config.ts
│
├── src/                       # 现有 TypeScript 代码（可复用）
│   └── models/
│       └── tri-state-asset.ts # 三态资产模型
│
└── docker/                    # Docker 配置
    ├── docker-compose.yml
    ├── Dockerfile.backend
    └── Dockerfile.frontend
```

---

## 3. 后端架构设计

### 3.1 AutoGen Runtime 集成

```python
# backend/app/core/autogen_client.py
from autogen import AutoGen, Agent, Tool, Flow
from typing import Dict, Any, List

class AutoGenClient:
    """AutoGen Runtime 封装客户端"""
    
    def __init__(self, config: Dict[str, Any]):
        self.client = AutoGen(api_key=config['api_key'])
        self.model_router = ModelRouter(config['models'])
    
    async def create_agent(
        self, 
        name: str, 
        model: str, 
        tools: List[Tool],
        system_prompt: str
    ) -> Agent:
        """创建 Agent 实例"""
        return self.client.agent(
            name=name,
            model=model,
            tools=tools,
            system_prompt=system_prompt
        )
    
    async def create_flow(self, agents: List[Agent]) -> Flow:
        """创建 Flow 编排"""
        return self.client.flow(agents=agents)
```

### 3.2 Agent 基类设计

```python
# backend/app/agents/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from autogen import Agent, Tool

class BaseAgent(ABC):
    """Agent 基类"""
    
    def __init__(self, name: str, model: str, tools: List[Tool] = None):
        self.name = name
        self.model = model
        self.tools = tools or []
        self.system_prompt = self._build_system_prompt()
    
    @abstractmethod
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        pass
    
    @abstractmethod
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理输入上下文，返回结果"""
        pass
    
    def get_tools(self) -> List[Tool]:
        """获取 Agent 可用的工具"""
        return self.tools
```

### 3.3 多模型专家 Agent 实现

```python
# backend/app/agents/log_agent.py
from .base import BaseAgent
from typing import Dict, Any

class LogAgent(BaseAgent):
    """日志分析专家 - 使用 glm-5 模型"""
    
    def __init__(self, tools: List[Tool]):
        super().__init__(
            name="LogAgent",
            model="glm-5",
            tools=tools
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资深的 SRE 日志分析专家。
        
你的职责是：
1. 解析和分析运行态日志
2. 提取异常栈、URL、类路径等关键信息
3. 识别异常模式和潜在问题

输出格式要求：
- exception_type: 异常类型
- exception_message: 异常消息
- stack_trace: 堆栈跟踪
- suspected_components: 可疑组件列表
- confidence: 置信度 (0-1)
"""
    
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理日志分析"""
        runtime_asset = context.get('runtime_asset', {})
        # 调用 AutoGen Runtime 进行分析
        result = await self.agent.run(
            input={"logs": runtime_asset.get('rawLogs', [])}
        )
        return result
```

```python
# backend/app/agents/domain_agent.py
from .base import BaseAgent

class DomainAgent(BaseAgent):
    """领域映射专家 - 使用 glm-5 模型"""
    
    def __init__(self, tools: List[Tool]):
        super().__init__(
            name="DomainAgent",
            model="glm-5",
            tools=tools
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位 DDD 领域建模专家。

你的职责是：
1. 将运行态异常映射到领域模型
2. 识别涉及的聚合根和限界上下文
3. 分析跨域影响

输出格式要求：
- domain: 所属领域
- bounded_context: 限界上下文
- aggregate_root: 聚合根
- affected_entities: 受影响实体
- cross_domain_impact: 跨域影响分析
"""
```

```python
# backend/app/agents/code_agent.py
from .base import BaseAgent

class CodeAgent(BaseAgent):
    """代码分析专家 - 使用 glm-5 模型"""
    
    def __init__(self, tools: List[Tool]):
        super().__init__(
            name="CodeAgent",
            model="glm-5",
            tools=tools
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资深的代码分析专家。

你的职责是：
1. 分析代码层面的根因
2. 构建证据链
3. 提出修复建议

输出格式要求：
- root_cause: 根因假设
- evidence_chain: 证据链
- code_location: 代码位置
- fix_suggestion: 修复建议
- confidence: 置信度
"""
```

### 3.4 辩论机制实现

```python
# backend/app/flows/debate_flow.py
from typing import Dict, Any, List
from autogen import Flow

class DebateFlow:
    """辩论流程编排"""
    
    def __init__(
        self,
        code_agent,
        critic_agent,
        rebuttal_agent,
        judge_agent
    ):
        self.code_agent = code_agent
        self.critic_agent = critic_agent
        self.rebuttal_agent = rebuttal_agent
        self.judge_agent = judge_agent
        self.max_rounds = 3
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行辩论流程"""
        
        # 第一阶段：独立分析
        initial_analysis = await self.code_agent.process(context)
        
        debate_history = [{
            "round": 0,
            "agent": "CodeAgent",
            "content": initial_analysis
        }]
        
        # 多轮辩论
        for round_num in range(1, self.max_rounds + 1):
            # 第二阶段：交叉质疑
            criticism = await self.critic_agent.process({
                **context,
                "previous_analysis": initial_analysis,
                "debate_history": debate_history
            })
            
            debate_history.append({
                "round": round_num,
                "agent": "CriticAgent",
                "content": criticism
            })
            
            # 第三阶段：反驳修正
            rebuttal = await self.rebuttal_agent.process({
                **context,
                "criticism": criticism,
                "debate_history": debate_history
            })
            
            debate_history.append({
                "round": round_num,
                "agent": "RebuttalAgent",
                "content": rebuttal
            })
            
            # 检查是否达成共识
            if rebuttal.get("consensus_reached"):
                break
        
        # 第四阶段：最终裁决
        final_judgment = await self.judge_agent.process({
            **context,
            "debate_history": debate_history
        })
        
        return {
            "debate_history": debate_history,
            "final_judgment": final_judgment,
            "total_rounds": len([h for h in debate_history if h["agent"] == "CriticAgent"])
        }
```

---

## 4. 前端架构设计

### 4.1 技术栈

- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **UI 组件库**: Ant Design 5.x
- **状态管理**: Zustand
- **数据请求**: TanStack Query
- **图表**: ECharts / D3.js
- **图谱可视化**: React Flow / Cytoscape.js

### 4.2 核心组件设计

```tsx
// frontend/src/components/DebateViewer/index.tsx
import React from 'react';
import { Timeline, Card, Tag, Typography } from 'antd';
import type { DebateRound } from '@/types';

interface DebateViewerProps {
  debateHistory: DebateRound[];
  currentRound: number;
  isLive: boolean;
}

export const DebateViewer: React.FC<DebateViewerProps> = ({
  debateHistory,
  currentRound,
  isLive
}) => {
  const getAgentColor = (agent: string) => {
    const colors: Record<string, string> = {
      'CodeAgent': 'blue',
      'CriticAgent': 'red',
      'RebuttalAgent': 'green',
      'JudgeAgent': 'purple'
    };
    return colors[agent] || 'default';
  };

  return (
    <div className="debate-viewer">
      <Timeline
        items={debateHistory.map((round, index) => ({
          color: index === currentRound && isLive ? 'processing' : 'gray',
          children: (
            <Card size="small">
              <div className="debate-header">
                <Tag color={getAgentColor(round.agent)}>
                  {round.agent}
                </Tag>
                <Typography.Text type="secondary">
                  Round {round.round}
                </Typography.Text>
              </div>
              <Typography.Paragraph>
                {round.content.summary}
              </Typography.Paragraph>
              {round.content.confidence && (
                <Tag>置信度: {(round.content.confidence * 100).toFixed(1)}%</Tag>
              )}
            </Card>
          )
        }))}
      />
    </div>
  );
};
```

### 4.3 页面结构

```tsx
// frontend/src/pages/Incident/index.tsx
import React from 'react';
import { Layout, Steps } from 'antd';
import { IncidentInput } from '@/components/IncidentInput';
import { AssetCollector } from '@/components/AssetCollector';
import { DebateViewer } from '@/components/DebateViewer';
import { ReportView } from '@/components/ReportView';

export const IncidentPage: React.FC = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [incidentData, setIncidentData] = useState(null);

  return (
    <Layout.Content className="incident-page">
      <Steps
        current={currentStep}
        items={[
          { title: '输入故障信息' },
          { title: '资产采集' },
          { title: 'AI 辩论分析' },
          { title: '生成报告' }
        ]}
      />
      
      <div className="step-content">
        {currentStep === 0 && (
          <IncidentInput onSubmit={(data) => {
            setIncidentData(data);
            setCurrentStep(1);
          }} />
        )}
        
        {currentStep === 1 && (
          <AssetCollector 
            incident={incidentData}
            onComplete={() => setCurrentStep(2)}
          />
        )}
        
        {currentStep === 2 && (
          <DebateViewer 
            incidentId={incidentData.id}
            onComplete={() => setCurrentStep(3)}
          />
        )}
        
        {currentStep === 3 && (
          <ReportView incidentId={incidentData.id} />
        )}
      </div>
    </Layout.Content>
  );
};
```

---

## 5. 数据流设计

### 5.1 故障分析流程

```mermaid
sequenceDiagram
    participant User as 用户
    participant Frontend as 前端
    participant API as API Gateway
    participant Flow as Flow Engine
    participant LogAgent as LogAgent
    participant DomainAgent as DomainAgent
    participant CodeAgent as CodeAgent
    participant CriticAgent as CriticAgent
    participant RebuttalAgent as RebuttalAgent
    participant JudgeAgent as JudgeAgent
    participant DB as 数据库

    User->>Frontend: 输入故障日志
    Frontend->>API: POST /api/incidents
    API->>DB: 创建故障记录
    API->>Flow: 启动分析流程
    
    Flow->>LogAgent: 分析日志
    LogAgent-->>Flow: 结构化异常信息
    
    Flow->>DomainAgent: 领域映射
    DomainAgent-->>Flow: 领域上下文
    
    Flow->>CodeAgent: 代码分析
    CodeAgent-->>Flow: 初始根因假设
    
    loop 辩论轮次
        Flow->>CriticAgent: 质疑分析
        CriticAgent-->>Flow: 质疑意见
        Flow->>RebuttalAgent: 反驳修正
        RebuttalAgent-->>Flow: 修正后的分析
    end
    
    Flow->>JudgeAgent: 最终裁决
    JudgeAgent-->>Flow: 最终结论
    
    Flow->>DB: 保存分析结果
    Flow-->>API: 返回报告
    API-->>Frontend: 返回分析报告
    Frontend-->>User: 展示结果
```

### 5.2 三态资产融合流程

```mermaid
flowchart LR
    subgraph 运行态
        A1[应用日志]
        A2[JVM监控]
        A3[Trace信息]
        A4[慢SQL]
    end
    
    subgraph 开发态
        B1[Git仓库]
        B2[聚合根]
        B3[Controller]
        B4[Repository]
    end
    
    subgraph 设计态
        C1[领域模型]
        C2[接口设计]
        C3[数据库设计]
        C4[历史案例]
    end
    
    subgraph 融合引擎
        D[资产融合服务]
        E[关联分析]
        F[图谱构建]
    end
    
    subgraph 输出
        G[融合上下文]
        H[关联关系图]
        I[关键发现]
    end
    
    A1 --> D
    A2 --> D
    A3 --> D
    A4 --> D
    
    B1 --> D
    B2 --> D
    B3 --> D
    B4 --> D
    
    C1 --> D
    C2 --> D
    C3 --> D
    C4 --> D
    
    D --> E
    E --> F
    F --> G
    F --> H
    F --> I
```

---

## 6. API 接口设计

### 6.1 RESTful API 规范

```
# 故障管理
POST   /api/v1/incidents              # 创建故障
GET    /api/v1/incidents              # 获取故障列表
GET    /api/v1/incidents/:id          # 获取故障详情
PUT    /api/v1/incidents/:id          # 更新故障
DELETE /api/v1/incidents/:id          # 删除故障

# 资产管理
POST   /api/v1/assets/runtime         # 上传运行态资产
POST   /api/v1/assets/development     # 上传开发态资产
POST   /api/v1/assets/design          # 上传设计态资产
GET    /api/v1/assets/fusion/:incidentId  # 获取资产融合结果

# 辩论流程
POST   /api/v1/debates                # 启动辩论
GET    /api/v1/debates/:id            # 获取辩论状态
GET    /api/v1/debates/:id/history    # 获取辩论历史
POST   /api/v1/debates/:id/intervene  # 人工干预

# 报告
GET    /api/v1/reports/:incidentId    # 获取分析报告
POST   /api/v1/reports/:incidentId/export  # 导出报告

# WebSocket
WS     /ws/debates/:id                # 实时辩论流
```

### 6.2 核心数据结构

```typescript
// 故障创建请求
interface CreateIncidentRequest {
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  runtimeAsset: RuntimeAsset;
  metadata?: Record<string, any>;
}

// 辩论结果
interface DebateResult {
  incidentId: string;
  debateHistory: DebateRound[];
  finalJudgment: {
    rootCause: string;
    evidenceChain: string[];
    fixSuggestion: string;
    impactAnalysis: string;
    riskLevel: 'critical' | 'high' | 'medium' | 'low';
    rollbackRecommended: boolean;
    responsibleTeam: string;
  };
  confidence: number;
  createdAt: string;
}

// 分析报告
interface AnalysisReport {
  incidentId: string;
  summary: string;
  rootCause: string;
  evidenceChain: EvidenceItem[];
  fixSuggestion: FixSuggestion[];
  impactAnalysis: ImpactAnalysis;
  riskAssessment: RiskAssessment;
  debateSummary: DebateSummary;
  generatedAt: string;
}
```

---

## 7. 部署架构

### 7.1 容器化部署

```yaml
# docker/docker-compose.yml
version: '3.8'

services:
  backend:
    build:
      context: ../backend
      dockerfile: ../docker/Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/sre_debate
      - REDIS_URL=redis://redis:6379
      - NEO4J_URI=bolt://neo4j:7687
      - LLM_API_KEY=${LLM_API_KEY}
    depends_on:
      - postgres
      - redis
      - neo4j

  frontend:
    build:
      context: ../frontend
      dockerfile: ../docker/Dockerfile.frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=sre_debate
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    volumes:
      - redis_data:/data

  neo4j:
    image: neo4j:5
    environment:
      - NEO4J_AUTH=neo4j/password
    volumes:
      - neo4j_data:/data

volumes:
  postgres_data:
  redis_data:
  neo4j_data:
```

### 7.2 生产环境架构

```mermaid
graph TB
    subgraph 负载均衡层
        LB[Nginx Load Balancer]
    end

    subgraph 前端服务
        FE1[Frontend Pod 1]
        FE2[Frontend Pod 2]
    end

    subgraph 后端服务
        BE1[Backend Pod 1]
        BE2[Backend Pod 2]
        BE3[Backend Pod 3]
    end

    subgraph Worker服务
        W1[Celery Worker 1]
        W2[Celery Worker 2]
    end

    subgraph 数据层
        PG[(PostgreSQL Cluster)]
        RD[(Redis Cluster)]
        NJ[(Neo4j Cluster)]
        VDB[(Vector DB)]
    end

    subgraph AI服务
        OC[LLM API]
        LLM[LLM Models]
    end

    LB --> FE1
    LB --> FE2
    FE1 --> BE1
    FE1 --> BE2
    FE2 --> BE2
    FE2 --> BE3
    
    BE1 --> PG
    BE2 --> PG
    BE3 --> PG
    
    BE1 --> RD
    BE2 --> RD
    
    BE1 --> NJ
    BE2 --> NJ
    
    W1 --> PG
    W2 --> PG
    W1 --> VDB
    W2 --> VDB
    
    BE1 --> OC
    BE2 --> OC
    W1 --> OC
    W2 --> OC
    
    OC --> LLM
```

---

## 8. 安全与治理

### 8.1 安全措施

1. **认证授权**
   - JWT Token 认证
   - RBAC 权限控制
   - API Key 管理

2. **数据安全**
   - 敏感信息脱敏
   - 传输加密 (TLS)
   - 存储加密

3. **访问控制**
   - IP 白名单
   - 请求限流
   - 审计日志

### 8.2 治理机制

1. **模型调用治理**
   - 调用频率限制
   - 成本监控
   - 超时控制

2. **人工审核**
   - 高风险决策人工确认
   - 审核流程配置
   - 审计追踪

---

## 9. 实施计划

### 阶段一：基础框架搭建

- [ ] 初始化后端项目结构
- [ ] 集成 AutoGen Runtime
- [ ] 实现基础 Agent 框架
- [ ] 搭建数据库和缓存
- [ ] 实现基础 API

### 阶段二：核心功能开发

- [ ] 实现 LogAgent 和日志解析工具
- [ ] 实现 DomainAgent 和 DDD 分析工具
- [ ] 实现 CodeAgent 和 Git 工具
- [ ] 实现三态资产融合服务
- [ ] 实现辩论流程编排

### 阶段三：前端开发

- [ ] 初始化 React 项目
- [ ] 实现故障输入组件
- [ ] 实现辩论可视化组件
- [ ] 实现报告展示组件
- [ ] 实现资产图谱组件

### 阶段四：集成测试

- [ ] 单元测试
- [ ] 集成测试
- [ ] 性能测试
- [ ] 安全测试

### 阶段五：部署上线

- [ ] 容器化配置
- [ ] CI/CD 流程
- [ ] 生产环境部署
- [ ] 监控告警配置

---

## 10. 附录

### 10.1 AutoGen Runtime 使用示例

```python
from autogen import AutoGen, Agent, Tool, Flow

# 初始化客户端
client = AutoGen(api_key="your-api-key")

# 定义工具
@tool
def search_code(query: str) -> str:
    """搜索代码库"""
    # 实现代码搜索逻辑
    return "search results..."

# 创建 Agent
code_agent = client.agent(
    name="CodeExpert",
    model="glm-5",
    tools=[search_code],
    system_prompt="你是一位代码分析专家..."
)

# 创建 Flow
flow = client.flow(
    agents=[log_agent, domain_agent, code_agent],
    context={"incident_id": "INC-001"}
)

# 执行 Flow
result = await flow.run()
```

### 10.2 模型配置参考

```yaml
# config/models.yaml
options:
  baseURL: https://coding.dashscope.aliyuncs.com/v1
  apiKey: sk-sp-5abc4c1d85414988979e90771e112f2f

models:
  glm-5:
    name: glm-5
```
