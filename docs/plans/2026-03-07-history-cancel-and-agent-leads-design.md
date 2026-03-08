# History Cancel And Agent Leads Design

## Goal

完成两项修正：
1. 修复历史记录页在取消分析后仍显示“分析中”的状态漂移。
2. 将责任田映射后的接口、代码、数据库、监控等线索整理为统一的 investigation leads，并由系统注入到主 Agent 分发与各分析 Agent 的自主定位上下文中。

## Scope

本次只做：
- cancel 链路的状态一致性修复
- investigation leads 生成与注入
- LogAgent / DomainAgent / CodeAgent / DatabaseAgent / MetricsAgent / ChangeAgent / RunbookAgent 的上下文增强
- 命令审计事件增强

本次不做：
- 新 Agent 类型
- 全新前端页面
- 新外部系统接入
- RBAC 与审批流重构

## Problem 1: Cancel Status Drift

当前 `/debates/{session_id}/cancel` 只更新 `DebateSession.status=cancelled`，但没有同步 `Incident.status`，导致历史记录页刷新后仍可能读到 `IncidentStatus.ANALYZING`。

修正策略：
- API cancel 与 WS cancel 均同步更新 incident 为 `closed`
- 历史记录页继续以 incident 为主，但状态将与 session 一致
- 保留 session event log 中的 `session_cancelled` 审计事件

## Problem 2: Agent Investigation Leads

当前系统已经有责任田映射与部分命令增强，但能力是碎片化的：
- `interface_mapping` 中已有 `matched_endpoint / database_tables / code_artifacts`
- `agent_tool_context_service` 会按 agent 提供不同工具上下文
- `langgraph_runtime` 已对 DatabaseAgent 做过表名补充

问题在于：
- 缺少统一的结构化线索对象
- 主 Agent 命令没有系统性携带接口、类名、表名、监控项等 leads
- 各 Agent 没有统一按“已知线索 -> 主动扩展定位”工作

## Design: Investigation Leads

新增 `investigation_leads`，在资产采集完成后由后端统一生成并写入：
- `context["investigation_leads"]`
- `assets["investigation_leads"]`
- `asset_interface_mapping_completed` 或后续事件中的摘要字段

建议字段：
- `api_endpoints`
- `service_names`
- `code_artifacts`
- `class_names`
- `database_tables`
- `monitor_items`
- `dependency_services`
- `domain`
- `aggregate`
- `owner_team`
- `owner`
- `trace_ids`
- `error_keywords`

## Design: Main Agent + System Injection

采用“主 Agent 给方向，系统强制注入线索，子 Agent 自主扩展”的模式：
- 主 Agent 继续决定参与 Agent 与高层任务
- 系统根据 `investigation_leads` 对各 Agent command 做 enrichment
- 系统将对应 leads 注入 tool context 与 skill hints
- 子 Agent 结合 command + tool context 主动展开分析

## Design: Agent-Specific Lead Injection

- `LogAgent`
  - 注入：接口、trace_id、错误关键词、日志片段
  - 目标：重建错误时间线，定位日志证据链
- `DomainAgent`
  - 注入：接口、领域、聚合、依赖服务、责任田信息
  - 目标：还原业务链路与责任边界
- `CodeAgent`
  - 注入：接口、service、code artifacts、class_names
  - 目标：检索代码路径与热点实现
- `DatabaseAgent`
  - 注入：表名、接口、数据库相关关键词
  - 目标：查询表 meta / 索引 / 慢 SQL / 阻塞线索
- `MetricsAgent`
  - 注入：监控项、服务、接口、错误窗口
  - 目标：抽取异常时序窗口与关键指标
- `ChangeAgent`
  - 注入：服务、接口、代码 artifact
  - 目标：关联故障窗口前后的变更
- `RunbookAgent`
  - 注入：领域、接口、错误类型、责任团队
  - 目标：匹配相似案例与 SOP

## Audit Requirements

需要保证可解释：
- `agent_command_issued` 中包含 leads 摘要
- tool audit 能看出检索是否使用了这些 leads
- 前端链路图与会话回放可展示“为什么该 Agent 会去查这些信息”

## Files

- Cancel status:
  - `backend/app/api/debates.py`
  - `backend/app/api/ws_debates.py`
  - `frontend/src/pages/History/index.tsx`
- Investigation leads:
  - `backend/app/services/debate_service.py`
  - `backend/app/runtime/langgraph_runtime.py`
  - `backend/app/services/agent_tool_context_service.py`
- Docs:
  - `docs/agents/agent-catalog.md`
