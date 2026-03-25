# 问题影响面分析专家设计（Brainstorming）

> 范围：在现有 LangGraph 多 Agent RCA 运行时中新增独立的 `ImpactAnalysisAgent`，用于分析故障影响面。  
> 目标：从问题描述、报错日志、告警信息、责任田映射和其他专家证据中，稳定输出“影响了哪些功能、哪些接口、多少用户”的结构化结论。  
> 时间：2026-03-25

---

## 1. 背景与问题

当前系统已经具备：

- `ProblemAnalysisAgent` 负责拆解和派单；
- `LogAgent / DomainAgent / CodeAgent / MetricsAgent / ChangeAgent` 等专家负责根因取证；
- `JudgeAgent` 最终输出 `impact_analysis`，但现状主要停留在：
  - `affected_services`
  - `business_impact`

这意味着系统虽然能给出“有影响”的结论，但还缺少一个专门负责“影响面量化”的专家，导致以下问题：

1. “哪些功能受影响”通常散落在 `DomainAgent` 或 `JudgeAgent` 的自然语言中，不稳定。  
2. “哪些接口受影响”缺少统一结构，前端和报告无法稳定消费。  
3. “影响了多少用户”经常只能给模糊文字，无法区分“已量化”“估算”“暂无法量化”。  
4. 责任田映射虽然已经存在，但没有被系统化地转化为 blast radius 分析。  

---

## 2. 目标与非目标

### 2.1 目标

新增独立的 `ImpactAnalysisAgent`，承担以下职责：

- 从 incident 文本、日志、告警、责任田映射和专家证据中分析问题影响范围；
- 同时输出两层视图：
  - 功能级总览
  - 接口级明细
- 对用户影响给出两类结果：
  - 明确量化值（measured）
  - 基于现有证据的估算值（estimated）
- 在无法量化时明确说明缺失证据和补证方向；
- 将结构化结果稳定接入 `JudgeAgent`、报告生成和前端展示。

### 2.2 非目标

第一版不做以下内容：

- 不新增外部数据源依赖或独立数据库；
- 不引入新的线上查询工具；
- 不做“精确到用户 ID 列表”的枚举；
- 不替代 `DomainAgent` 的责任归属判断；
- 不替代 `MetricsAgent` 的监控异常取证。

---

## 3. 方案对比

### 方案 A：新增独立 `ImpactAnalysisAgent`（推荐）

思路：

- 新增正式专家，与 `LogAgent / DomainAgent / MetricsAgent` 并列；
- `ProblemAnalysisAgent` 在首轮或第二轮根据责任田和错误特征派发影响面分析任务；
- `JudgeAgent` 直接消费其结构化输出。

优点：

- 职责单一，和 `DomainAgent`、`JudgeAgent` 不混淆；
- 易于加 benchmark、治理规则和前端展示；
- 输出结构稳定，便于报告和 API 复用。

缺点：

- 需要同步改 catalog、schema、routing、前端映射和测试。

### 方案 B：并入 `DomainAgent`

思路：

- 让 `DomainAgent` 同时负责责任边界和影响面。

优点：

- 代码改动较少。

缺点：

- 单个专家职责过重；
- 输出容易混在业务链路分析里，难以稳定消费；
- 后续想补估算逻辑、benchmark 和专项 UI 时会越来越耦合。

### 方案 C：只在 Judge 前做聚合

思路：

- 不新增专家，只在 `JudgeAgent` 前做规则聚合。

优点：

- 初始改动最少。

缺点：

- 缺少独立证据链，不可解释；
- 很难被主 Agent 定向派单；
- 无法形成独立专家视角和后续扩展能力。

### 推荐结论

采用 **方案 A**，但实现策略分两阶段：

1. 第一阶段：新增正式 `ImpactAnalysisAgent`，只消费现有证据，不新增复杂工具。  
2. 第二阶段：视效果补专项 skill/tool 或更强的用户量化数据源。  

---

## 4. 新专家职责设计

### 4.1 职责边界

`ImpactAnalysisAgent` 负责回答：

- 哪些业务功能受影响？
- 哪些接口或入口受影响？
- 涉及哪些服务、责任田和上下游依赖？
- 影响了多少用户？
  - 已量化值是多少？
  - 如果不能量化，估算值是多少？
  - 估算依据是什么？
  - 置信度是多少？

它不负责：

- 最终根因归属裁决；
- 代码层修复方案；
- 责任归属的最终判责。

### 4.2 输入来源

第一版只使用现有运行时已具备的数据：

- incident 原始文本；
- 报错日志摘要、错误关键词、traceId；
- 告警标题/告警内容/监控项；
- 责任田映射结果：
  - `api_endpoints`
  - `dependency_services`
  - `service_names`
  - `monitor_items`
  - `error_keywords`
- 其他专家输出：
  - `LogAgent`
  - `DomainAgent`
  - `MetricsAgent`
  - `ChangeAgent`

### 4.3 输出结构

建议 `ImpactAnalysisAgent` 输出以下结构：

```json
{
  "chat_message": "",
  "analysis": "",
  "conclusion": "",
  "impact_summary": {
    "affected_functions": [
      {
        "name": "",
        "severity": "critical|high|medium|low",
        "evidence_basis": [],
        "affected_interfaces": [],
        "user_impact": {
          "measured_users": null,
          "estimated_users": null,
          "affected_ratio": "",
          "estimation_basis": "",
          "confidence": 0.0
        }
      }
    ],
    "affected_interfaces": [
      {
        "endpoint": "",
        "method": "",
        "service": "",
        "error_signal": "",
        "related_function": "",
        "user_impact": {
          "measured_users": null,
          "estimated_users": null,
          "confidence": 0.0
        }
      }
    ],
    "affected_services": [],
    "affected_user_scope": {
      "measured_users": null,
      "estimated_users": null,
      "affected_ratio": "",
      "estimation_basis": "",
      "confidence": 0.0
    },
    "severity": "critical|high|medium|low",
    "unknowns": []
  },
  "evidence_chain": [],
  "follow_up_actions": [],
  "confidence": 0.0
}
```

---

## 5. 分析策略

### 5.1 功能级影响识别

基于以下信号聚合：

- incident 描述中的业务动作词；
- 责任田映射中的 domain / aggregate / api endpoints；
- `DomainAgent` 给出的业务链路；
- `LogAgent` 和 `MetricsAgent` 给出的异常入口与时间窗。

输出结果应聚合成业务功能，而不是只列服务名。

### 5.2 接口级影响识别

基于以下信号识别：

- responsibility mapping 命中的 `api_endpoints`；
- 日志中的路径、方法、HTTP 状态码、错误关键词；
- 网关、应用日志、trace 中出现的入口接口；
- 同一故障窗口里高相关的失败接口。

### 5.3 用户影响量化

遵循三段式策略：

1. **有明确证据时输出 measured**
   - 如告警面板、监控数据、日志聚合中已经出现明确的用户数/请求数/订单数/失败数。

2. **无明确证据但可推断时输出 estimated**
   - 基于故障持续时间、接口流量、失败率、功能覆盖范围、责任田服务特征进行估算。

3. **无法推断时明确 unknown**
   - 输出“暂无法量化”，并列出缺失证据与补证建议。

### 5.4 置信度原则

- `measured_users` 置信度通常高于 `estimated_users`；
- 如果功能影响和接口影响都来自同一弱证据，不允许给高置信度；
- 若责任田映射置信度低，需同步下调影响面结论置信度。

---

## 6. 运行时接入设计

### 6.1 Agent Catalog

在 `docs/agents/agent-catalog.md` 中新增：

- `ImpactAnalysisAgent`
- phase: `analysis`
- 说明其依赖责任田映射、日志/告警、同伴证据

### 6.2 Prompt / Schema

需要在运行时增加：

- 专家输出 schema；
- commander 对它的命令模板；
- Judge 对其结果的消费方式。

### 6.3 调度策略

建议调度规则：

- `quick`
  - 默认只在检测到明确业务入口、日志错误和责任田映射都存在时触发；
- `standard`
  - 在首轮责任田映射后默认触发；
- `deep`
  - 与 `DomainAgent / MetricsAgent` 形成更强协同，必要时第二轮补证。

### 6.4 Judge 收敛

`JudgeAgent` 继续输出统一的 `final_judgment.impact_analysis`，但数据源将增强为：

- `ImpactAnalysisAgent` 的结构化结果作为主来源；
- 其他专家结果作为辅助校验来源。

---

## 7. 前端展示设计

建议新增两层展示：

1. 专家过程区
   - 显示 `ImpactAnalysisAgent` 的过程消息、功能级摘要、接口级摘要和估算依据。

2. 结果区
   - 在最终 `impact_analysis` 之外增加可展开明细：
     - 受影响功能
     - 受影响接口
     - 用户影响量化与估算依据

第一版要求与现有前端兼容，不移除现有 `affected_services / business_impact` 字段。

---

## 8. 风险与约束

1. 第一版没有新的专用工具，用户影响量化会偏保守。  
2. 如果 incident 文本质量太差，功能级映射可能依赖 `DomainAgent` 较重。  
3. 如果没有监控量化指标，`estimated_users` 必须明确标注估算口径，避免被误认为实测值。  
4. 需要保证新增字段是“增量兼容”，不能破坏现有 API 和报告渲染。  

---

## 9. 验收标准

满足以下条件视为第一版完成：

1. 新增 `ImpactAnalysisAgent` 并成功接入 LangGraph runtime。  
2. 主 Agent 可以对它下发结构化命令。  
3. Judge 能消费其结果并生成增强版 `impact_analysis`。  
4. 前端能看到该专家的过程和最终影响面明细。  
5. 至少新增 1 个 benchmark case 和一组后端回归测试。  
6. 对于“有量化证据 / 只能估算 / 无法量化”三类场景都能给出稳定输出。  
