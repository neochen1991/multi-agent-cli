# 多模型辩论式 SRE 智能体平台 - 实施路线图

## 1. 项目概览

### 1.1 项目目标
基于 OpenCode SDK 构建多模型辩论式 SRE 智能体平台，实现三态资产融合与 AI 技术委员会决策系统。

### 1.2 技术栈确认
| 层级 | 技术选型 |
|------|----------|
| 后端框架 | Python 3.11+ / FastAPI |
| AI SDK | OpenCode SDK |
| 前端框架 | React 18 / TypeScript / Vite |
| UI 组件库 | Ant Design 5.x |
| 主数据库 | PostgreSQL 15 |
| 图数据库 | Neo4j 5.x |
| 缓存/队列 | Redis 7 / Celery |
| 向量数据库 | Milvus / Qdrant |
| 容器化 | Docker / Docker Compose |

---

## 2. 阶段一：基础框架搭建

### 2.1 后端项目初始化

#### 任务清单
- [ ] 创建 Python 项目结构
- [ ] 配置 pyproject.toml 和依赖管理
- [ ] 集成 FastAPI 框架
- [ ] 配置日志系统
- [ ] 配置环境变量管理

#### 目录结构
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理
│   ├── dependencies.py         # 依赖注入
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py           # 路由汇总
│   │   ├── incidents.py        # 故障事件 API
│   │   ├── assets.py           # 资产管理 API
│   │   ├── debates.py          # 辩论流程 API
│   │   └── reports.py          # 报告 API
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py             # Agent 基类
│   │   └── registry.py         # Agent 注册中心
│   ├── tools/
│   │   ├── __init__.py
│   │   └── base.py             # Tool 基类
│   ├── models/
│   │   ├── __init__.py
│   │   ├── incident.py
│   │   ├── asset.py
│   │   └── report.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── opencode_service.py # OpenCode 服务
│   └── core/
│       ├── __init__.py
│       ├── opencode_client.py  # OpenCode SDK 封装
│       └── model_router.py     # 模型路由
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_main.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

#### 核心代码示例

**pyproject.toml**
```toml
[project]
name = "sre-debate-platform"
version = "0.1.0"
description = "多模型辩论式 SRE 智能体平台"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "opencode-sdk>=0.1.0",
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",
    "redis>=5.0.0",
    "celery>=5.3.0",
    "httpx>=0.26.0",
    "python-multipart>=0.0.6",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "black>=24.1.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
]
```

**app/main.py**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.router import api_router

app = FastAPI(
    title="SRE Debate Platform",
    description="多模型辩论式 SRE 智能体平台 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### 2.2 OpenCode SDK 集成

#### 任务清单
- [ ] 封装 OpenCode 客户端
- [ ] 实现模型路由器
- [ ] 创建 Agent 基类
- [ ] 创建 Tool 基类

#### 核心代码

**app/core/opencode_client.py**
```python
from typing import Dict, Any, List, Optional
from opencode import OpenCode, Agent, Tool, Flow
from app.config import settings

class OpenCodeClient:
    """OpenCode SDK 封装客户端"""
    
    _instance: Optional["OpenCodeClient"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.client = OpenCode(api_key=settings.OPENCODE_API_KEY)
        self._agents: Dict[str, Agent] = {}
        self._initialized = True
    
    async def create_agent(
        self,
        name: str,
        model: str,
        tools: List[Tool],
        system_prompt: str,
        **kwargs
    ) -> Agent:
        """创建或获取 Agent 实例"""
        if name in self._agents:
            return self._agents[name]
        
        agent = self.client.agent(
            name=name,
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            **kwargs
        )
        self._agents[name] = agent
        return agent
    
    async def create_flow(
        self,
        agents: List[Agent],
        context: Dict[str, Any]
    ) -> Flow:
        """创建 Flow 编排"""
        return self.client.flow(agents=agents, context=context)
    
    async def run_flow(self, flow: Flow) -> Dict[str, Any]:
        """执行 Flow"""
        result = await flow.run()
        return result
```

**app/agents/base.py**
```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from opencode import Agent, Tool

from app.core.opencode_client import OpenCodeClient

class AgentResult(BaseModel):
    """Agent 执行结果"""
    agent_name: str
    success: bool
    data: Dict[str, Any]
    confidence: float = 0.0
    reasoning: Optional[str] = None
    error: Optional[str] = None

class BaseAgent(ABC):
    """Agent 基类"""
    
    def __init__(
        self,
        name: str,
        model: str,
        tools: List[Tool] = None,
        system_prompt: str = None
    ):
        self.name = name
        self.model = model
        self.tools = tools or []
        self.system_prompt = system_prompt or self._build_system_prompt()
        self._agent: Optional[Agent] = None
    
    @abstractmethod
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        pass
    
    @abstractmethod
    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """处理输入上下文，返回结果"""
        pass
    
    async def get_agent(self) -> Agent:
        """获取或创建 Agent 实例"""
        if self._agent is None:
            client = OpenCodeClient()
            self._agent = await client.create_agent(
                name=self.name,
                model=self.model,
                tools=self.tools,
                system_prompt=self.system_prompt
            )
        return self._agent
    
    def register_tool(self, tool: Tool):
        """注册工具"""
        self.tools.append(tool)
```

### 2.3 数据库设计

#### 任务清单
- [ ] 设计数据库 Schema
- [ ] 配置 SQLAlchemy 模型
- [ ] 实现数据库迁移
- [ ] 配置 Neo4j 连接

#### PostgreSQL Schema

```sql
-- 故障表
CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    runtime_asset JSONB,
    development_asset JSONB,
    design_asset JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 辩论记录表
CREATE TABLE debates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id),
    status VARCHAR(20) DEFAULT 'pending',
    current_round INTEGER DEFAULT 0,
    max_rounds INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- 辩论轮次表
CREATE TABLE debate_rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    debate_id UUID REFERENCES debates(id),
    round_number INTEGER NOT NULL,
    agent_name VARCHAR(50) NOT NULL,
    agent_role VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    confidence DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 分析报告表
CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id),
    debate_id UUID REFERENCES debates(id),
    root_cause TEXT,
    evidence_chain JSONB,
    fix_suggestions JSONB,
    impact_analysis JSONB,
    risk_level VARCHAR(20),
    confidence DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 案例库表
CREATE TABLE case_library (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    root_cause TEXT,
    solution TEXT,
    keywords TEXT[],
    embedding VECTOR(1536),  -- 如果使用 pgvector
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. 阶段二：核心功能开发

### 3.1 Agent 实现

#### 任务清单
- [ ] 实现 LogAgent（日志分析）
- [ ] 实现 DomainAgent（领域映射）
- [ ] 实现 CodeAgent（代码分析）
- [ ] 实现 CriticAgent（质疑）
- [ ] 实现 RebuttalAgent（反驳）
- [ ] 实现 JudgeAgent（裁决）

#### LogAgent 实现

**app/agents/log_agent.py**
```python
from typing import Dict, Any, List
from opencode import tool

from app.agents.base import BaseAgent, AgentResult

class LogAgent(BaseAgent):
    """日志分析专家 - 使用 kimi-k2.5 模型"""
    
    def __init__(self, tools: List = None):
        super().__init__(
            name="LogAgent",
            model="kimi-k2.5",
            tools=tools or []
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资深的 SRE 日志分析专家。

你的职责是：
1. 解析和分析运行态日志
2. 提取异常栈、URL、类路径等关键信息
3. 识别异常模式和潜在问题
4. 关联 JVM 监控指标

分析步骤：
1. 识别异常类型和消息
2. 解析堆栈跟踪，定位关键代码位置
3. 分析线程状态
4. 关联 Trace 信息
5. 识别慢 SQL

输出 JSON 格式：
{
    "exception_type": "异常类型",
    "exception_message": "异常消息",
    "stack_trace_summary": "堆栈摘要",
    "suspected_components": ["可疑组件列表"],
    "related_urls": ["相关URL"],
    "slow_queries": ["慢SQL列表"],
    "jvm_anomalies": ["JVM异常指标"],
    "confidence": 0.85
}"""
    
    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """处理日志分析"""
        runtime_asset = context.get('runtime_asset', {})
        
        agent = await self.get_agent()
        
        # 构建输入
        input_data = {
            "raw_logs": runtime_asset.get('rawLogs', []),
            "exception": runtime_asset.get('exception'),
            "jvm_metrics": runtime_asset.get('jvmMetrics'),
            "traces": runtime_asset.get('traces', []),
            "slow_sqls": runtime_asset.get('slowSQLs', [])
        }
        
        # 调用 Agent
        response = await agent.run(input=input_data)
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=response.data,
            confidence=response.data.get('confidence', 0.0),
            reasoning=response.data.get('reasoning')
        )
```

#### CodeAgent 实现

**app/agents/code_agent.py**
```python
from typing import Dict, Any, List
from opencode import tool

from app.agents.base import BaseAgent, AgentResult
from app.tools.git_tool import GitTool
from app.tools.code_search_tool import CodeSearchTool

class CodeAgent(BaseAgent):
    """代码分析专家 - 使用 kimi-k2.5 模型"""
    
    def __init__(self):
        # 注册代码相关工具
        tools = [
            GitTool(),
            CodeSearchTool(),
        ]
        super().__init__(
            name="CodeAgent",
            model="kimi-k2.5",
            tools=tools
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资级的代码分析专家，精通 Java Spring 和 DDD 架构。

你的职责是：
1. 分析代码层面的根因
2. 构建证据链
3. 定位问题代码
4. 提出修复建议

分析步骤：
1. 根据异常栈定位代码位置
2. 分析相关类和方法
3. 检查聚合根和领域服务
4. 分析数据库操作
5. 构建根因假设

输出 JSON 格式：
{
    "root_cause_hypothesis": "根因假设",
    "evidence_chain": [
        {
            "step": 1,
            "description": "证据描述",
            "code_location": "文件:行号",
            "snippet": "代码片段"
        }
    ],
    "affected_files": ["受影响文件列表"],
    "fix_suggestion": {
        "description": "修复建议描述",
        "code_changes": [
            {
                "file": "文件路径",
                "change_type": "modify",
                "suggestion": "修改建议"
            }
        ]
    },
    "confidence": 0.85
}"""
    
    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """处理代码分析"""
        development_asset = context.get('development_asset', {})
        log_analysis = context.get('log_analysis', {})
        
        agent = await self.get_agent()
        
        input_data = {
            "repository": development_asset.get('repository'),
            "exception_info": log_analysis.data.get('exception_type'),
            "stack_trace": log_analysis.data.get('stack_trace_summary'),
            "suspected_components": log_analysis.data.get('suspected_components', [])
        }
        
        response = await agent.run(input=input_data)
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=response.data,
            confidence=response.data.get('confidence', 0.0),
            reasoning=response.data.get('reasoning')
        )
```

### 3.2 辩论流程实现

#### 任务清单
- [ ] 实现辩论协调器
- [ ] 实现上下文管理器
- [ ] 实现辩论轮次控制
- [ ] 实现共识检测机制

**app/flows/debate_flow.py**
```python
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from app.agents.base import AgentResult
from app.agents.code_agent import CodeAgent
from app.agents.critic_agent import CriticAgent
from app.agents.rebuttal_agent import RebuttalAgent
from app.agents.judge_agent import JudgeAgent

@dataclass
class DebateRound:
    """辩论轮次"""
    round_number: int
    agent_name: str
    agent_role: str
    content: Dict[str, Any]
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class DebateResult:
    """辩论结果"""
    incident_id: str
    debate_history: List[DebateRound]
    final_judgment: Optional[Dict[str, Any]]
    total_rounds: int
    consensus_reached: bool
    completed_at: datetime = field(default_factory=datetime.now)

class DebateOrchestrator:
    """辩论协调器"""
    
    def __init__(
        self,
        code_agent: CodeAgent,
        critic_agent: CriticAgent,
        rebuttal_agent: RebuttalAgent,
        judge_agent: JudgeAgent,
        max_rounds: int = 3,
        consensus_threshold: float = 0.85
    ):
        self.code_agent = code_agent
        self.critic_agent = critic_agent
        self.rebuttal_agent = rebuttal_agent
        self.judge_agent = judge_agent
        self.max_rounds = max_rounds
        self.consensus_threshold = consensus_threshold
    
    async def execute(
        self,
        incident_id: str,
        context: Dict[str, Any]
    ) -> DebateResult:
        """执行辩论流程"""
        debate_history: List[DebateRound] = []
        current_analysis: Optional[AgentResult] = None
        
        # 第一阶段：独立分析
        initial_analysis = await self.code_agent.process(context)
        current_analysis = initial_analysis
        
        debate_history.append(DebateRound(
            round_number=0,
            agent_name="CodeAgent",
            agent_role="analyst",
            content=initial_analysis.data,
            confidence=initial_analysis.confidence
        ))
        
        consensus_reached = False
        
        # 多轮辩论
        for round_num in range(1, self.max_rounds + 1):
            # 第二阶段：交叉质疑
            criticism = await self.critic_agent.process({
                **context,
                "previous_analysis": current_analysis.data,
                "debate_history": [h.__dict__ for h in debate_history]
            })
            
            debate_history.append(DebateRound(
                round_number=round_num,
                agent_name="CriticAgent",
                agent_role="critic",
                content=criticism.data,
                confidence=criticism.confidence
            ))
            
            # 第三阶段：反驳修正
            rebuttal = await self.rebuttal_agent.process({
                **context,
                "criticism": criticism.data,
                "previous_analysis": current_analysis.data,
                "debate_history": [h.__dict__ for h in debate_history]
            })
            
            debate_history.append(DebateRound(
                round_number=round_num,
                agent_name="RebuttalAgent",
                agent_role="rebuttal",
                content=rebuttal.data,
                confidence=rebuttal.confidence
            ))
            
            # 更新当前分析
            current_analysis = rebuttal
            
            # 检查是否达成共识
            if self._check_consensus(criticism, rebuttal):
                consensus_reached = True
                break
        
        # 第四阶段：最终裁决
        final_judgment = await self.judge_agent.process({
            **context,
            "debate_history": [h.__dict__ for h in debate_history],
            "final_analysis": current_analysis.data
        })
        
        debate_history.append(DebateRound(
            round_number=len(debate_history),
            agent_name="JudgeAgent",
            agent_role="judge",
            content=final_judgment.data,
            confidence=final_judgment.confidence
        ))
        
        return DebateResult(
            incident_id=incident_id,
            debate_history=debate_history,
            final_judgment=final_judgment.data,
            total_rounds=len([h for h in debate_history if h.agent_role == "critic"]),
            consensus_reached=consensus_reached
        )
    
    def _check_consensus(
        self,
        criticism: AgentResult,
        rebuttal: AgentResult
    ) -> bool:
        """检查是否达成共识"""
        # 如果反驳后置信度超过阈值，且批评意见已被充分回应
        if rebuttal.confidence >= self.consensus_threshold:
            # 检查批评意见是否已被回应
            unaddressed = rebuttal.data.get('unaddressed_critiques', [])
            if len(unaddressed) == 0:
                return True
        return False
```

### 3.3 工具层实现

#### 任务清单
- [ ] 实现日志解析工具
- [ ] 实现 Git 操作工具
- [ ] 实现 DDD 分析工具
- [ ] 实现数据库查询工具
- [ ] 实现案例库检索工具

**app/tools/log_parser.py**
```python
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from opencode import tool

@dataclass
class ParsedException:
    exception_type: str
    message: str
    stack_trace: List[str]
    cause: Optional[str] = None

@dataclass
class ParsedLog:
    timestamp: str
    level: str
    logger: str
    message: str
    thread: Optional[str] = None
    trace_id: Optional[str] = None

class LogParserTool:
    """日志解析工具"""
    
    # Java 异常栈正则
    EXCEPTION_PATTERN = re.compile(
        r'^(\w+(?:\.\w+)*(?:Exception|Error|Throwable)):\s*(.*)$'
    )
    STACK_TRACE_PATTERN = re.compile(
        r'^\s+at\s+([\w.]+)\.([\w<>]+)\(([\w.]+):(\d+)\)$'
    )
    
    # 日志格式正则
    LOG_PATTERN = re.compile(
        r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+'
        r'\[(\w+)\]\s+'
        r'\[([\w.-]+)\]\s+'
        r'(?:\[([^\]]+)\]\s+)?'
        r'(.*)$'
    )
    
    @tool
    def parse_exception(self, log_content: str) -> Dict[str, Any]:
        """解析异常信息
        
        Args:
            log_content: 日志内容
            
        Returns:
            解析后的异常信息
        """
        lines = log_content.strip().split('\n')
        exceptions = []
        current_exception = None
        stack_trace = []
        
        for line in lines:
            # 检查是否是异常开头
            match = self.EXCEPTION_PATTERN.match(line)
            if match:
                if current_exception:
                    current_exception.stack_trace = stack_trace
                    exceptions.append(current_exception)
                
                current_exception = ParsedException(
                    exception_type=match.group(1),
                    message=match.group(2),
                    stack_trace=[]
                )
                stack_trace = []
            # 检查是否是堆栈行
            elif current_exception:
                stack_match = self.STACK_TRACE_PATTERN.match(line)
                if stack_match:
                    stack_trace.append({
                        'class': stack_match.group(1),
                        'method': stack_match.group(2),
                        'file': stack_match.group(3),
                        'line': int(stack_match.group(4))
                    })
        
        if current_exception:
            current_exception.stack_trace = stack_trace
            exceptions.append(current_exception)
        
        return {
            'exceptions': [
                {
                    'type': e.exception_type,
                    'message': e.message,
                    'stack_trace': e.stack_trace,
                    'cause': e.cause
                }
                for e in exceptions
            ]
        }
    
    @tool
    def parse_log_line(self, log_line: str) -> Dict[str, Any]:
        """解析单行日志
        
        Args:
            log_line: 日志行
            
        Returns:
            解析后的日志信息
        """
        match = self.LOG_PATTERN.match(log_line)
        if match:
            return {
                'timestamp': match.group(1),
                'level': match.group(2),
                'logger': match.group(3),
                'thread': match.group(4),
                'message': match.group(5)
            }
        return {'raw': log_line}
    
    @tool
    def extract_urls(self, content: str) -> List[str]:
        """提取 URL
        
        Args:
            content: 内容
            
        Returns:
            URL 列表
        """
        url_pattern = re.compile(r'https?://[^\s]+|/[a-zA-Z0-9/_-]+')
        return url_pattern.findall(content)
    
    @tool
    def extract_class_names(self, content: str) -> List[str]:
        """提取类名
        
        Args:
            content: 内容
            
        Returns:
            类名列表
        """
        class_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)*)\b')
        return list(set(class_pattern.findall(content)))
```

---

## 4. 阶段三：前端开发

### 4.1 前端项目初始化

#### 任务清单
- [ ] 创建 React + TypeScript 项目
- [ ] 配置 Vite 构建
- [ ] 集成 Ant Design
- [ ] 配置路由
- [ ] 配置状态管理

#### 目录结构
```
frontend/
├── src/
│   ├── main.tsx               # 入口文件
│   ├── App.tsx                # 根组件
│   ├── vite-env.d.ts
│   ├── api/                   # API 请求
│   │   ├── client.ts          # Axios 客户端
│   │   ├── incidents.ts       # 故障 API
│   │   ├── debates.ts         # 辩论 API
│   │   └── reports.ts         # 报告 API
│   ├── components/            # 组件
│   │   ├── common/            # 通用组件
│   │   ├── IncidentInput/     # 故障输入
│   │   ├── AssetCollector/    # 资产采集
│   │   ├── DebateViewer/      # 辩论可视化
│   │   ├── ReportView/        # 报告展示
│   │   └── AssetGraph/        # 资产图谱
│   ├── pages/                 # 页面
│   │   ├── Home/              # 首页
│   │   ├── Incident/          # 故障分析
│   │   ├── Assets/            # 资产管理
│   │   └── History/           # 历史记录
│   ├── stores/                # 状态管理
│   │   ├── incidentStore.ts
│   │   └── debateStore.ts
│   ├── hooks/                 # 自定义 Hooks
│   │   ├── useIncident.ts
│   │   └── useDebate.ts
│   ├── types/                 # 类型定义
│   │   ├── incident.ts
│   │   ├── asset.ts
│   │   └── debate.ts
│   └── utils/                 # 工具函数
│       └── format.ts
├── package.json
├── vite.config.ts
├── tsconfig.json
└── index.html
```

### 4.2 核心组件实现

#### 任务清单
- [ ] 实现故障输入组件
- [ ] 实现资产采集组件
- [ ] 实现辩论可视化组件
- [ ] 实现报告展示组件
- [ ] 实现资产图谱组件

**src/components/DebateViewer/index.tsx**
```tsx
import React, { useEffect, useState } from 'react';
import { Timeline, Card, Tag, Typography, Space, Progress, Button } from 'antd';
import {
  UserOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined
} from '@ant-design/icons';
import type { DebateRound, DebateStatus } from '@/types';

const { Text, Paragraph } = Typography;

interface DebateViewerProps {
  incidentId: string;
  onComplete?: (result: any) => void;
}

export const DebateViewer: React.FC<DebateViewerProps> = ({
  incidentId,
  onComplete
}) => {
  const [debateHistory, setDebateHistory] = useState<DebateRound[]>([]);
  const [currentRound, setCurrentRound] = useState(0);
  const [status, setStatus] = useState<DebateStatus>('pending');
  const [isLive, setIsLive] = useState(true);

  // WebSocket 连接
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/debates/${incidentId}`);
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'round_complete') {
        setDebateHistory(prev => [...prev, data.round]);
        setCurrentRound(data.round.round_number);
      } else if (data.type === 'debate_complete') {
        setStatus('completed');
        setIsLive(false);
        onComplete?.(data.result);
      }
    };
    
    return () => ws.close();
  }, [incidentId, onComplete]);

  const getAgentConfig = (agentName: string) => {
    const configs: Record<string, { color: string; icon: React.ReactNode; role: string }> = {
      'LogAgent': { color: 'blue', icon: <RobotOutlined />, role: '日志分析专家' },
      'DomainAgent': { color: 'cyan', icon: <RobotOutlined />, role: '领域映射专家' },
      'CodeAgent': { color: 'geekblue', icon: <RobotOutlined />, role: '代码分析专家' },
      'CriticAgent': { color: 'red', icon: <UserOutlined />, role: '架构质疑专家' },
      'RebuttalAgent': { color: 'green', icon: <RobotOutlined />, role: '技术反驳专家' },
      'JudgeAgent': { color: 'purple', icon: <UserOutlined />, role: '技术委员会主席' },
    };
    return configs[agentName] || { color: 'default', icon: <RobotOutlined />, role: '专家' };
  };

  return (
    <div className="debate-viewer">
      <div className="debate-header">
        <Space size="large">
          <Text strong>辩论状态：</Text>
          <Tag 
            icon={status === 'completed' ? <CheckCircleOutlined /> : <SyncOutlined spin />}
            color={status === 'completed' ? 'success' : 'processing'}
          >
            {status === 'completed' ? '已完成' : '进行中'}
          </Tag>
          <Text>当前轮次：{currentRound}</Text>
        </Space>
      </div>

      <Timeline
        items={debateHistory.map((round, index) => {
          const config = getAgentConfig(round.agent_name);
          return {
            dot: config.icon,
            color: index === debateHistory.length - 1 && isLive ? 'processing' : 'gray',
            children: (
              <Card 
                size="small"
                title={
                  <Space>
                    <Tag color={config.color}>{round.agent_name}</Tag>
                    <Text type="secondary">{config.role}</Text>
                    <Text type="secondary">Round {round.round_number}</Text>
                  </Space>
                }
                extra={
                  round.confidence && (
                    <Progress 
                      percent={Math.round(round.confidence * 100)} 
                      size="small"
                      style={{ width: 100 }}
                    />
                  )
                }
              >
                <Paragraph ellipsis={{ rows: 3, expandable: true }}>
                  {round.content.summary || JSON.stringify(round.content, null, 2)}
                </Paragraph>
                
                {round.content.root_cause && (
                  <div className="round-detail">
                    <Text strong>根因假设：</Text>
                    <Text>{round.content.root_cause}</Text>
                  </div>
                )}
                
                {round.content.evidence_chain && (
                  <div className="evidence-chain">
                    <Text strong>证据链：</Text>
                    <ul>
                      {round.content.evidence_chain.map((e: any, i: number) => (
                        <li key={i}>{e.description}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </Card>
            )
          };
        })}
      />
    </div>
  );
};
```

---

## 5. 阶段四：集成测试

### 5.1 测试策略

#### 任务清单
- [ ] 编写单元测试
- [ ] 编写集成测试
- [ ] 编写 E2E 测试
- [ ] 性能测试
- [ ] 安全测试

### 5.2 测试用例

**tests/agents/test_log_agent.py**
```python
import pytest
from app.agents.log_agent import LogAgent
from app.tools.log_parser import LogParserTool

@pytest.fixture
def log_agent():
    return LogAgent(tools=[LogParserTool()])

@pytest.fixture
def sample_runtime_asset():
    return {
        "rawLogs": [
            "2024-01-15 10:30:45.123 ERROR [OrderService] [http-nio-8080-exec-1] NullPointerException: Cannot invoke method on null object",
            "    at com.example.order.service.OrderService.createOrder(OrderService.java:125)",
            "    at com.example.order.controller.OrderController.create(OrderController.java:45)"
        ],
        "exception": {
            "type": "NullPointerException",
            "message": "Cannot invoke method on null object"
        }
    }

@pytest.mark.asyncio
async def test_log_agent_process(log_agent, sample_runtime_asset):
    """测试 LogAgent 处理"""
    context = {"runtime_asset": sample_runtime_asset}
    
    result = await log_agent.process(context)
    
    assert result.success
    assert result.agent_name == "LogAgent"
    assert "exception_type" in result.data
    assert result.confidence > 0
```

---

## 6. 阶段五：部署上线

### 6.1 部署清单

- [ ] 编写 Dockerfile
- [ ] 配置 docker-compose
- [ ] 配置 CI/CD 流水线
- [ ] 配置监控告警
- [ ] 配置日志收集

### 6.2 Docker 配置

**docker/Dockerfile.backend**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY app/ ./app/

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker/Dockerfile.frontend**
```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## 7. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| OpenCode SDK API 变更 | 高 | 封装 SDK 调用，便于适配 |
| 模型响应延迟 | 中 | 异步处理，WebSocket 推送 |
| 辩论无法达成共识 | 中 | 设置最大轮次，人工介入 |
| 敏感信息泄露 | 高 | 日志脱敏，权限控制 |
| 成本超预算 | 中 | 模型调用限流，成本监控 |

---

## 8. 验收标准

### 8.1 功能验收
- [ ] 支持日志上传和解析
- [ ] 支持三态资产融合
- [ ] 支持多模型辩论流程
- [ ] 支持生成分析报告
- [ ] 支持实时辩论可视化

### 8.2 性能验收
- [ ] API 响应时间 < 500ms
- [ ] 辩论流程完成时间 < 5min
- [ ] 支持 100 并发用户

### 8.3 质量验收
- [ ] 单元测试覆盖率 > 80%
- [ ] 无高危安全漏洞
- [ ] 代码通过 Lint 检查
