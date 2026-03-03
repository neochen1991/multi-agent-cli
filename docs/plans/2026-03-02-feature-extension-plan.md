# 智能运维平台功能扩展方案

## 一、主流 AIOps 平台功能对比

### 1.1 云厂商平台对比

| 功能模块 | 阿里云 ARMS | 腾讯云观测 | 华为云 AOM | Datadog | PagerDuty | 本项目现状 |
|----------|-------------|------------|------------|---------|-----------|------------|
| **根因分析** | ✅ AI驱动 | ✅ AI驱动 | ✅ AI驱动 | ✅ ML驱动 | ✅ 事件智能 | ✅ 多Agent辩论 |
| **告警降噪** | ✅ 智能聚合 | ✅ 告警归并 | ✅ 告警压缩 | ✅ Alert Correlation | ✅ Alert Grouping | ❌ 缺失 |
| **异常检测** | ✅ 无阈值检测 | ✅ 动态基线 | ✅ 智能基线 | ✅ Anomaly Detection | ✅ ML检测 | ❌ 缺失 |
| **拓扑感知** | ✅ 应用拓扑 | ✅ 服务拓扑 | ✅ 调用链拓扑 | ✅ Service Map | ✅ Service Graph | ⚠️ 静态资产映射 |
| **故障自愈** | ✅ 自动化执行 | ✅ 自愈脚本 | ✅ 自动恢复 | ✅ Workflow | ✅ Automation | ❌ 缺失 |
| **变更关联** | ✅ 变更分析 | ✅ 发布关联 | ✅ 变更溯源 | ✅ Deployment Tracking | ✅ Change Events | ⚠️ ChangeAgent定义但未实现 |
| **案例库** | ✅ 知识库 | ✅ 经验库 | ✅ 故障案例 | ⚠️ Notes | ✅ Postmortem | ❌ 缺失 |
| **预测分析** | ✅ 容量预测 | ✅ 趋势预测 | ✅ 智能预测 | ✅ Forecasting | ❌ | ❌ 缺失 |
| **协作流程** | ✅ 工单集成 | ✅ 流程编排 | ✅ 工单系统 | ✅ Integration | ✅ Incident Response | ❌ 缺失 |
| **监控集成** | ✅ 全栈监控 | ✅ 全栈监控 | ✅ 全栈监控 | ✅ 原生监控 | ⚠️ 第三方 | ⚠️ 仅日志解析 |

### 1.2 核心差距分析

```
本项目当前能力                              行业标准能力
┌─────────────────────┐                 ┌─────────────────────┐
│ ✅ 多Agent辩论分析   │                 │ ✅ AI根因分析        │
│ ✅ 日志解析         │                 │ ✅ 告警智能降噪      │
│ ✅ 报告生成         │                 │ ✅ 异常自动检测      │
│ ⚠️ 静态资产映射     │  ─────差距─────> │ ✅ 动态拓扑感知      │
│ ⚠️ 工具门控机制     │                 │ ✅ 故障自愈执行      │
│ ❌ 无告警管理       │                 │ ✅ 变更关联分析      │
│ ❌ 无异常检测       │                 │ ✅ 历史案例库        │
│ ❌ 无自愈能力       │                 │ ✅ 容量预测          │
│ ❌ 无案例库         │                 │ ✅ 协作工作流        │
└─────────────────────┘                 └─────────────────────┘
```

---

## 二、功能扩展方案

### 2.1 告警管理中心 (P0 - 高价值)

**问题**: 当前系统只能被动接收故障信息，无法主动管理和降噪告警

**参考方案**:
- 阿里云 ARMS: 智能告警聚合，相似告警合并
- PagerDuty: Alert Grouping + deduplication

**功能设计**:

```python
# backend/app/services/alert_service.py

class AlertManagementService:
    """告警管理服务"""

    async def ingest_alert(self, alert: Alert) -> AlertProcessResult:
        """告警接入与处理"""
        # 1. 去重：基于指纹（服务+错误类型+时间窗口）
        fingerprint = self._generate_fingerprint(alert)
        if await self._is_duplicate(fingerprint):
            return AlertProcessResult(action="deduplicated", fingerprint=fingerprint)

        # 2. 聚合：相似告警合并
        similar_alerts = await self._find_similar(alert)
        if similar_alerts:
            await self._aggregate_alerts(alert, similar_alerts)
            return AlertProcessResult(action="aggregated", group_id=...)

        # 3. 分级：基于历史数据和规则
        severity = await self._classify_severity(alert)

        # 4. 关联：检查是否与变更、其他告警相关
        correlations = await self._find_correlations(alert)

        # 5. 路由：决定是否触发分析
        if severity >= Severity.HIGH:
            await self._trigger_analysis(alert)

        return AlertProcessResult(action="created", alert=alert, severity=severity)

    async def suppress_noise(self, alert: Alert) -> bool:
        """告警降噪"""
        # 基于规则的降噪
        if alert.matches_suppression_rules():
            return True

        # 基于ML的降噪（历史相同告警未处理且自恢复）
        if await self._is_transient(alert):
            return True

        return False
```

**API 设计**:
```
POST /api/v1/alerts/          # 接收告警
GET  /api/v1/alerts/          # 告警列表
POST /api/v1/alerts/{id}/suppress  # 屏蔽告警
POST /api/v1/alerts/{id}/acknowledge  # 确认告警
GET  /api/v1/alerts/stats     # 告警统计
```

**前端页面**:
- 告警列表（支持聚合视图）
- 告警规则配置
- 降噪规则管理
- 告警趋势图表

---

### 2.2 异常检测引擎 (P0 - 高价值)

**问题**: 依赖用户主动输入故障信息，无法主动发现异常

**参考方案**:
- Datadog: Anomaly Detection based on ML
- 阿里云 ARMS: 无阈值智能检测

**功能设计**:

```python
# backend/app/services/anomaly_detection_service.py

class AnomalyDetectionService:
    """异常检测服务"""

    def __init__(self):
        self.detectors = {
            "metric": MetricAnomalyDetector(),      # 指标异常
            "log": LogAnomalyDetector(),            # 日志异常
            "trace": TraceAnomalyDetector(),        # 调用链异常
            "behavior": BehaviorAnomalyDetector(),  # 行为异常
        }

    async def detect_metric_anomaly(
        self,
        metric_name: str,
        values: list[float],
        timestamps: list[datetime]
    ) -> AnomalyResult:
        """指标异常检测"""
        detector = self.detectors["metric"]

        # 1. 季节性分解
        trend, seasonal, residual = detector.decompose(values)

        # 2. 基于残差检测异常点
        anomalies = detector.detect_anomalies(residual, threshold=3.0)

        # 3. 计算异常置信度
        confidence = detector.calculate_confidence(anomalies)

        return AnomalyResult(
            metric_name=metric_name,
            anomalies=anomalies,
            confidence=confidence,
            baseline={"trend": trend, "seasonal": seasonal}
        )

    async def detect_log_anomaly(self, log_entries: list[dict]) -> AnomalyResult:
        """日志异常检测"""
        # 1. 日志模式聚类
        patterns = await self._cluster_log_patterns(log_entries)

        # 2. 检测新模式（未见过的日志模式）
        new_patterns = await self._detect_new_patterns(patterns)

        # 3. 检测频率异常（某模式突然增多）
        frequency_anomalies = await self._detect_frequency_anomalies(patterns)

        # 4. 关键词异常（ERROR/FATAL 突增）
        keyword_anomalies = await self._detect_keyword_anomalies(log_entries)

        return AnomalyResult(
            anomalies=new_patterns + frequency_anomalies + keyword_anomalies,
            patterns=patterns
        )
```

**集成方式**:
```python
# 与现有系统集成
class MetricsAgent:
    """指标分析Agent - 增强"""

    async def analyze(self, context: AnalysisContext) -> AgentOutput:
        # 1. 获取指标数据
        metrics = await self._fetch_metrics(context.service_name, context.time_range)

        # 2. 异常检测
        anomalies = await anomaly_detection_service.detect_metric_anomaly(metrics)

        # 3. 结合业务上下文分析
        analysis = await self._analyze_with_context(anomalies, context)

        return AgentOutput(
            findings=analysis,
            evidence=anomalies.to_evidence()
        )
```

---

### 2.3 故障自愈系统 (P1 - 核心能力)

**问题**: 分析结果只能给出建议，无法自动执行修复

**参考方案**:
- 阿里云: 自愈脚本 + 审批流程
- PagerDuty: Automation Actions

**功能设计**:

```python
# backend/app/services/self_healing_service.py

from enum import Enum
from typing import Callable

class HealingAction(Enum):
    """自愈动作类型"""
    RESTART_SERVICE = "restart_service"
    SCALE_OUT = "scale_out"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    CLEAR_CACHE = "clear_cache"
    KILL_PROCESS = "kill_process"
    EXECUTE_SCRIPT = "execute_script"

class SelfHealingService:
    """故障自愈服务"""

    # 预置自愈剧本
    HEALING_PLAYBOOKS = {
        "oom_restart": {
            "trigger": {"symptom": "OutOfMemoryError"},
            "action": HealingAction.RESTART_SERVICE,
            "approval_required": False,
            "rollback": True
        },
        "high_latency_scale": {
            "trigger": {"symptom": "latency_p99 > 1000ms", "duration": "5m"},
            "action": HealingAction.SCALE_OUT,
            "approval_required": True,
            "parameters": {"replicas": 2}
        },
        "deployment_rollback": {
            "trigger": {"symptom": "error_rate_spike", "after": "deployment"},
            "action": HealingAction.ROLLBACK_DEPLOYMENT,
            "approval_required": True,
            "rollback": False
        }
    }

    async def evaluate_healing_options(
        self,
        incident: Incident,
        analysis: AnalysisReport
    ) -> list[HealingOption]:
        """评估自愈选项"""
        options = []

        for playbook_id, playbook in self.HEALING_PLAYBOOKS.items():
            if self._matches_trigger(incident, analysis, playbook["trigger"]):
                option = HealingOption(
                    playbook_id=playbook_id,
                    action=playbook["action"],
                    description=self._get_description(playbook),
                    approval_required=playbook["approval_required"],
                    risk_level=self._assess_risk(playbook),
                    success_rate=await self._get_historical_success_rate(playbook_id)
                )
                options.append(option)

        return options

    async def execute_healing(
        self,
        option: HealingOption,
        approval_token: str | None = None
    ) -> HealingResult:
        """执行自愈动作"""
        # 1. 权限检查
        if option.approval_required and not approval_token:
            raise ApprovalRequiredError()

        # 2. 记录执行前状态（用于回滚）
        snapshot = await self._create_snapshot(option)

        # 3. 执行动作
        try:
            result = await self._execute_action(option)
            await self._record_success(option, result)
            return HealingResult(success=True, result=result)
        except Exception as e:
            # 4. 自动回滚
            if option.rollback:
                await self._rollback(snapshot)
            await self._record_failure(option, e)
            return HealingResult(success=False, error=str(e))

    async def _execute_action(self, option: HealingOption) -> dict:
        """执行具体动作"""
        executors: dict[HealingAction, Callable] = {
            HealingAction.RESTART_SERVICE: self._restart_service,
            HealingAction.SCALE_OUT: self._scale_out,
            HealingAction.ROLLBACK_DEPLOYMENT: self._rollback_deployment,
            HealingAction.CLEAR_CACHE: self._clear_cache,
            HealingAction.EXECUTE_SCRIPT: self._execute_script,
        }
        return await executors[option.action](option.parameters)
```

**前端集成**:
```tsx
// 在分析结果页面显示自愈选项
<HealingPanel>
  <Alert type="info">
    系统检测到以下自愈选项可用
  </Alert>

  <HealingOptionCard
    action="restart_service"
    description="重启异常服务"
    risk="low"
    successRate={95}
    onApprove={() => executeHealing(option)}
  />

  <HealingOptionCard
    action="rollback_deployment"
    description="回滚到上一版本"
    risk="medium"
    successRate={88}
    requiresApproval={true}
    onRequestApproval={() => requestApproval(option)}
  />
</HealingPanel>
```

---

### 2.4 动态拓扑感知 (P1)

**问题**: 当前资产映射是静态的，无法反映运行时调用关系

**参考方案**:
- Datadog: Service Map
- 阿里云 ARMS: 应用拓扑

**功能设计**:

```python
# backend/app/services/topology_service.py

class TopologyService:
    """拓扑感知服务"""

    async def build_runtime_topology(
        self,
        service_name: str,
        time_range: TimeRange
    ) -> ServiceTopology:
        """构建运行时服务拓扑"""
        # 1. 从调用链数据提取依赖关系
        traces = await self._fetch_traces(service_name, time_range)
        dependencies = self._extract_dependencies(traces)

        # 2. 从日志提取调用关系
        logs = await self._fetch_logs(service_name, time_range)
        call_relations = self._extract_call_relations(logs)

        # 3. 合并构建拓扑
        topology = ServiceTopology(
            nodes=await self._build_nodes(dependencies),
            edges=await self._build_edges(dependencies, call_relations),
            metrics=await self._collect_node_metrics(dependencies)
        )

        # 4. 检测拓扑变化
        changes = await self._detect_topology_changes(topology)

        return topology

    async def annotate_incident_topology(
        self,
        incident: Incident,
        topology: ServiceTopology
    ) -> AnnotatedTopology:
        """在拓扑上标注故障信息"""
        # 1. 定位故障节点
        fault_node = topology.find_node(incident.service_name)

        # 2. 标注传播路径
        propagation_path = await self._trace_fault_propagation(incident, topology)

        # 3. 高亮异常边
        anomalous_edges = await self._identify_anomalous_edges(incident, topology)

        return AnnotatedTopology(
            topology=topology,
            fault_node=fault_node,
            propagation_path=propagation_path,
            anomalous_edges=anomalous_edges
        )
```

**前端可视化**:
```tsx
// 使用 AntV G6 或 D3.js 绘制拓扑图
<ServiceTopologyGraph
  topology={annotatedTopology}
  highlightPath={faultPropagationPath}
  onNodeClick={(node) => showNodeDetails(node)}
  onEdgeClick={(edge) => showEdgeMetrics(edge)}
/>
```

---

### 2.5 案例知识库 (P1)

**问题**: 历史故障经验无法沉淀和复用

**参考方案**:
- PagerDuty: Postmortem Library
- 阿里云: 故障案例库

**功能设计**:

```python
# backend/app/services/case_library_service.py

from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

class CaseLibraryService:
    """案例知识库服务"""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.vectorstore = Chroma(
            embedding_function=self.embeddings,
            persist_directory="./data/case_library"
        )

    async def save_case(self, incident: Incident, report: Report) -> CaseEntry:
        """保存故障案例"""
        # 1. 提取关键信息
        case = CaseEntry(
            id=str(uuid.uuid4()),
            title=incident.title,
            symptoms=self._extract_symptoms(incident),
            root_cause=report.root_cause,
            solution=report.recommendations,
            timeline=report.timeline,
            metadata={
                "service": incident.service_name,
                "severity": incident.severity,
                "resolution_time": report.resolution_time,
                "tags": self._extract_tags(incident, report)
            }
        )

        # 2. 向量化存储
        doc = Document(
            page_content=f"{case.title}\n{case.symptoms}\n{case.root_cause}",
            metadata=case.metadata
        )
        await self.vectorstore.aadd_documents([doc])

        return case

    async def search_similar_cases(
        self,
        query: str,
        filters: dict | None = None,
        k: int = 5
    ) -> list[CaseMatch]:
        """搜索相似案例"""
        # 1. 向量相似度搜索
        results = await self.vectorstore.asimilarity_search_with_score(query, k=k*2)

        # 2. 过滤和排序
        matches = []
        for doc, score in results:
            if filters and not self._match_filters(doc.metadata, filters):
                continue
            matches.append(CaseMatch(
                case=self._load_case(doc.metadata["case_id"]),
                similarity=1 - score,
                matched_aspects=self._identify_matched_aspects(query, doc)
            ))

        return matches[:k]

    async def suggest_runbook(self, symptoms: list[str]) -> RunbookSuggestion:
        """基于案例推荐Runbook"""
        query = " ".join(symptoms)
        similar_cases = await self.search_similar_cases(query, k=3)

        # 提取共性解决方案
        common_solutions = self._extract_common_solutions(similar_cases)

        return RunbookSuggestion(
            recommended_steps=common_solutions,
            based_on_cases=[c.case.id for c in similar_cases],
            confidence=self._calculate_confidence(similar_cases)
        )
```

**增强 RunbookAgent**:
```python
class RunbookAgent(ExpertAgent):
    """RunbookAgent - 增强"""

    async def analyze(self, context: AnalysisContext) -> AgentOutput:
        # 1. 从案例库搜索相似案例
        similar_cases = await case_library_service.search_similar_cases(
            query=context.incident.description,
            filters={"service": context.incident.service_name}
        )

        # 2. 获取Runbook建议
        runbook = await case_library_service.suggest_runbook(context.symptoms)

        # 3. 生成处置建议
        recommendations = self._generate_recommendations(similar_cases, runbook)

        return AgentOutput(
            findings={
                "similar_cases": similar_cases,
                "runbook": runbook,
                "recommendations": recommendations
            }
        )
```

---

### 2.6 变更关联分析 (P1)

**问题**: 无法自动关联变更事件，需要人工排查

**参考方案**:
- Datadog: Deployment Tracking
- 阿里云: 变更溯源

**功能设计**:

```python
# backend/app/services/change_correlation_service.py

class ChangeCorrelationService:
    """变更关联服务"""

    async def correlate_incident_with_changes(
        self,
        incident: Incident,
        time_window_hours: int = 24
    ) -> ChangeCorrelationResult:
        """关联故障与变更"""
        # 1. 获取时间窗口内的变更
        changes = await self._fetch_recent_changes(
            incident.service_name,
            incident.environment,
            time_window_hours
        )

        # 2. 计算关联概率
        correlations = []
        for change in changes:
            probability = await self._calculate_correlation_probability(incident, change)
            if probability > 0.3:
                correlations.append(ChangeCorrelation(
                    change=change,
                    probability=probability,
                    reasoning=self._explain_correlation(incident, change)
                ))

        # 3. 排序返回
        correlations.sort(key=lambda x: x.probability, reverse=True)

        return ChangeCorrelationResult(
            incident_id=incident.id,
            correlations=correlations,
            recommendation=self._generate_recommendation(correlations)
        )

    async def _calculate_correlation_probability(
        self,
        incident: Incident,
        change: ChangeEvent
    ) -> float:
        """计算关联概率"""
        score = 0.0

        # 1. 时间接近度（故障发生在变更后 1 小时内概率最高）
        time_diff = (incident.created_at - change.timestamp).total_seconds() / 3600
        if time_diff < 0:
            return 0.0  # 变更在故障后
        if time_diff < 1:
            score += 0.4
        elif time_diff < 4:
            score += 0.2
        elif time_diff < 24:
            score += 0.1

        # 2. 服务匹配
        if change.service == incident.service_name:
            score += 0.3

        # 3. 历史相关性（该服务过去故障与变更的相关率）
        historical_rate = await self._get_historical_change_failure_rate(change.service)
        score += historical_rate * 0.2

        # 4. 变更类型权重
        type_weights = {
            "deployment": 0.1,
            "config_change": 0.15,
            "infrastructure": 0.2,
            "database_migration": 0.25
        }
        score += type_weights.get(change.type, 0.05)

        return min(score, 1.0)
```

---

### 2.7 协作工作流 (P2)

**问题**: 缺乏与现有运维流程的集成

**功能设计**:

```python
# backend/app/services/workflow_service.py

class WorkflowService:
    """协作工作流服务"""

    # 支持的通知渠道
    NOTIFICATION_CHANNELS = {
        "slack": SlackNotifier(),
        "dingtalk": DingTalkNotifier(),
        "wechat": WeChatNotifier(),
        "email": EmailNotifier(),
        "sms": SMSNotifier(),
    }

    async def create_incident_workflow(
        self,
        incident: Incident,
        analysis: AnalysisReport
    ) -> IncidentWorkflow:
        """创建故障处理工作流"""
        workflow = IncidentWorkflow(
            incident_id=incident.id,
            stages=[
                WorkflowStage(name="acknowledge", status="pending"),
                WorkflowStage(name="diagnosis", status="completed", result=analysis),
                WorkflowStage(name="resolution", status="pending"),
                WorkflowStage(name="verification", status="pending"),
                WorkflowStage(name="postmortem", status="pending"),
            ]
        )

        # 通知相关人员
        await self._notify_oncall(incident, analysis)

        return workflow

    async def _notify_oncall(self, incident: Incident, analysis: AnalysisReport):
        """通知值班人员"""
        # 1. 获取值班表
        oncall = await self._get_oncall_schedule(incident.service_name)

        # 2. 构建通知内容
        message = self._build_notification(incident, analysis)

        # 3. 根据严重程度选择通知渠道
        channels = self._select_channels(incident.severity)

        # 4. 发送通知
        for channel in channels:
            notifier = self.NOTIFICATION_CHANNELS[channel]
            await notifier.send(oncall.contacts, message)
```

---

### 2.8 容量预测 (P2)

**问题**: 无法提前预警资源瓶颈

**功能设计**:

```python
# backend/app/services/capacity_prediction_service.py

class CapacityPredictionService:
    """容量预测服务"""

    async def predict_capacity(
        self,
        service_name: str,
        metric_name: str = "cpu_usage",
        forecast_days: int = 7
    ) -> CapacityPrediction:
        """预测容量需求"""
        # 1. 获取历史数据
        history = await self._fetch_metric_history(
            service_name,
            metric_name,
            days=30
        )

        # 2. 时间序列预测
        forecast = await self._time_series_forecast(history, forecast_days)

        # 3. 识别瓶颈时间点
        bottleneck = self._find_bottleneck(forecast, threshold=0.8)

        # 4. 生成建议
        recommendations = self._generate_capacity_recommendations(forecast, bottleneck)

        return CapacityPrediction(
            service_name=service_name,
            metric_name=metric_name,
            current_usage=history[-1],
            forecast=forecast,
            bottleneck_date=bottleneck.date if bottleneck else None,
            recommendations=recommendations
        )
```

---

## 三、功能优先级矩阵

| 功能 | 用户价值 | 实现复杂度 | 依赖项 | 优先级 |
|------|----------|------------|--------|--------|
| 告警管理中心 | 高 | 中 | 无 | **P0** |
| 异常检测引擎 | 高 | 高 | 监控数据接入 | **P0** |
| 故障自愈系统 | 高 | 高 | 审批流程、执行器 | **P1** |
| 动态拓扑感知 | 中 | 中 | 调用链数据 | **P1** |
| 案例知识库 | 高 | 低 | 向量数据库 | **P1** |
| 变更关联分析 | 中 | 中 | 变更事件源 | **P1** |
| 协作工作流 | 中 | 中 | 通知渠道集成 | **P2** |
| 容量预测 | 低 | 高 | 历史数据 | **P2** |

---

## 四、技术实现依赖

### 4.1 数据接入

```yaml
# 需要接入的数据源
data_sources:
  metrics:
    - Prometheus
    - InfluxDB
    - CloudWatch

  logs:
    - ELK Stack
    - Loki
    - SLS

  traces:
    - Jaeger
    - Zipkin
    - SkyWalking

  events:
    - CI/CD Pipeline (Jenkins, GitLab CI)
    - Change Management System
    - Deployment Platform (K8s)
```

### 4.2 存储扩展

```yaml
# 存储需求
storage:
  vector_db:        # 案例库、日志模式
    - Milvus
    - Chroma
    - Pinecone

  time_series:      # 指标、异常检测
    - Prometheus
    - InfluxDB

  document:         # 案例、报告
    - MongoDB
    - Elasticsearch
```

### 4.3 集成接口

```yaml
# 外部系统集成
integrations:
  notification:
    - Slack Webhook
    - 钉钉机器人
    - 企业微信

  ticket:
    - JIRA
    - 飞书多维表格

  execution:
    - Kubernetes API
    - Ansible
    - Terraform
```

---

## 五、实施路线图

```
Phase 1 (Week 1-4): 核心能力补齐
├── 告警管理中心
│   ├── 告警接入 API
│   ├── 去重/聚合逻辑
│   └── 前端告警页面
├── 案例知识库
│   ├── 向量存储集成
│   ├── 案例入库流程
│   └── 相似案例检索
└── 变更关联分析
    ├── 变更事件接入
    └── 关联算法实现

Phase 2 (Week 5-8): 智能化增强
├── 异常检测引擎
│   ├── 指标异常检测
│   ├── 日志异常检测
│   └── 主动告警触发
├── 动态拓扑感知
│   ├── 调用链数据接入
│   ├── 拓扑构建算法
│   └── 前端拓扑可视化
└── 协作工作流
    ├── 通知渠道集成
    └── 工作流引擎

Phase 3 (Week 9-12): 自愈能力
├── 故障自愈系统
│   ├── 自愈剧本框架
│   ├── 执行器实现
│   ├── 审批流程
│   └── 回滚机制
└── 容量预测
    ├── 时序预测模型
    └── 预警通知
```

---

## 六、预期收益

| 指标 | 当前 | 预期改进 |
|------|------|----------|
| MTTR (平均修复时间) | ~60分钟 | 减少50% → ~30分钟 |
| 告警数量 | 原始 | 降噪70% |
| 故障发现方式 | 被动上报 | 主动检测占比 > 40% |
| 重复故障分析 | 每次重新分析 | 案例库匹配 > 60% |
| 自动修复比例 | 0% | 自愈成功率 > 30% |
| 分析准确率 | ~70% | 提升 > 85% |