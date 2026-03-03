# 2026-03-02 OpenDerisk 源码重点分析

仓库：`https://github.com/derisk-ai/OpenDerisk`

## 1. 总体判断

OpenDerisk 不是单体 demo，而是一个 **可产品化的 AI-SRE 平台骨架**，核心特征是：
1. Monorepo 分层清晰（core/ext/serve/app/client）。
2. ReAct 主控 Agent 的工程化能力强（循环保护、上下文压缩、阶段管理、报告生成）。
3. MCP 作为一等公民（gateway + serve api + tool 调用链）。
4. 场景化 Skill + Resource 设计（OpenRCA 场景驱动诊断）。

---

## 2. 代码分层与职责

## 2.1 `derisk-core`（内核层）
- 位置：`packages/derisk-core/src/derisk`
- 作用：
  - Agent 抽象、执行框架、模型适配、上下文管理、组件体系。
  - ReAct/Tool/Plan 的核心实现。
- 关键文件（已核验）：
  - `agent/expand/react_master_agent/react_master_agent.py`
  - `agent/expand/react_master_agent/phase_manager.py`
  - `agent/expand/react_master_agent/session_compaction.py`
  - `agent/expand/react_master_agent/doom_loop_detector.py`
  - `agent/expand/react_master_agent/report_generator.py`
  - `component.py`, `context/*`, `model/*`

## 2.2 `derisk-ext`（扩展层）
- 位置：`packages/derisk-ext/src/derisk_ext`
- 作用：
  - 场景 Agent、MCP gateway、RAG 知识源、数据源连接器等扩展能力。
- 关键文件：
  - `agent/agents/open_rca/resource/open_rca_resource.py`
  - `agent/agents/open_rca/skills/open_rca_diagnosis/SKILL.md`
  - `mcp/gateway.py`, `mcp/client.py`
  - `rag/knowledge/*`（多格式知识载入）

## 2.3 `derisk-serve`（服务层）
- 位置：`packages/derisk-serve/src/derisk_serve`
- 作用：
  - API 对外服务，Agent 聊天控制器、MCP 管理接口、持久化服务。
- 关键文件：
  - `agent/agents/controller.py`（MultiAgents 入口）
  - `agent/agents/chat/agent_chat_async.py`（异步会话）
  - `mcp/service/service.py`（MCP 注册、连通、工具调用）
  - `mcp/api/endpoints.py`（MCP 管理 API）

## 2.4 `derisk-app`（应用层）
- 位置：`packages/derisk-app/src/derisk_app`
- 作用：
  - 启动装配、路由挂载、组件初始化、静态资源挂载。
- 关键文件：
  - `derisk_server.py`（服务启动）
  - `app.py`（系统装配）
  - `openapi/api_v1`, `openapi/api_v2`

---

## 3. 主调用链（源码角度）

1. 进程启动：`derisk_server.py` -> `app.py`  
2. 应用装配：加载配置、注册组件、挂载 API、初始化模型与存储  
3. 对话入口：`derisk_serve/agent/agents/controller.py`  
4. 会话执行：`agent_chat`（sync/quick/background/async）  
5. Agent 内核：`ReActMasterAgent`（推理 + tool calling）  
6. 工具面：MCP tool pack / local tool / resource tool  
7. 结果面：work log + report generator + 前端可视化

---

## 4. ReActMaster 的工程化亮点

从 `react_master_agent.py` 与配套模块可确认：

1. 循环保护  
- `doom_loop_detector` 防“重复调用同工具导致死循环”。

2. 上下文治理  
- `session_compaction` 在上下文逼近阈值时做摘要压缩。
- `history_pruning` 清理历史，避免 token 爆炸。

3. 工具输出治理  
- 截断大输出，降低上下文污染与长响应延迟风险。

4. 阶段化执行  
- `phase_manager` 将任务划分探索/规划/执行/验证/报告阶段。

5. 报告内建  
- `report_generator` 支持 markdown/html/json/plain 多格式报告。

结论：它在“可持续运行”的工程能力上明显优于常见 ReAct demo。

---

## 5. MCP 设计亮点

从 `derisk-ext/mcp` 与 `derisk-serve/mcp` 可确认：

1. Gateway 化  
- `gateway.py` 处理注册、认证、消息转发与工具发现。

2. 服务化管理  
- `endpoints.py` 提供 create/update/delete/start/offline/connect/tool/list/tool/run。

3. 调用抽象  
- `service.py` 统一了 connect/list_tools/call_tool，支持 headers/token 合并。

4. 安全边界  
- API key 校验 + token 转 Authorization 的规范处理。

结论：MCP 在该仓库是“平台基础能力”，不是外挂功能。

---

## 6. OpenRCA 场景化能力

从 `open_rca_resource.py` 与 `open_rca_diagnosis/SKILL.md` 可确认：

1. 场景参数化  
- bank / telecom / market 场景及对应描述、数据路径。

2. 技能化方法论  
- 把 RCA 流程固化成阶段规范（预处理、异常检测、故障识别、根因定位）。

3. 规则化约束  
- 明确阈值计算、时区统一、日志分析规范、禁止事项。

结论：其优势在“可复制诊断流程”，便于团队标准化。

---

## 7. 对你项目最有价值的借鉴清单

## P0（必须先做）
1. 引入 `DoomLoopDetector + SessionCompaction + OutputTruncation` 三件套。  
2. 会话日志结构化：阶段、工具I/O、结论、耗时、置信度。  
3. 把现有 RCA 规则写成 Skill 文档，避免 prompt 漫游。

## P1（质量增强）
1. 主Agent接入阶段管理（探索->规划->执行->验证->报告）。  
2. 报告生成器拆成独立模块，支持多格式与前端友好渲染。  
3. 将“责任田映射”升级为 Resource，不再散落在 prompt 字符串。

## P2（平台化）
1. MCP 工具管理 API 化，统一启停、健康、鉴权、调用审计。  
2. 代码结构分层成 `core/ext/serve/app`，降低编排器复杂度。  
3. 引入快速会话/后台会话双通道（参考 quick/background/async chat）。

---

## 8. 不建议直接照搬的部分

1. OpenDerisk 体量较大，直接迁入会增加维护负担。  
2. 其历史包袱较重（多子包协同），你项目应选“模式迁移”而非“代码复制”。  
3. 先迁移“机制层能力”（循环保护、压缩、阶段、MCP接口）收益最高。

---

## 9. 结论

OpenDerisk 的核心价值不在“某个 Agent prompt”，而在以下四个工程机制：
1. 可持续推理机制（防循环、压缩、裁剪）  
2. 可治理工具机制（MCP 管理与调用）  
3. 可复用诊断机制（Skill + Resource）  
4. 可产品化交付机制（服务层 API + 报告与可视化）

如果你的目标是“生产问题根因定位系统”，这四块是最该优先迁移的能力。
