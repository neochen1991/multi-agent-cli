# 2026-03-02 12家公司方案 GitHub 源码深度解析（无源码则跳过）

## 1. 说明

本次按你的要求执行了两层核验：
1. 逐篇检查 12 篇文章正文中的 GitHub 链接（锚点 + 正文文本）。
2. 对识别到的 GitHub 仓库做源码级解析（目录、入口、核心模块、关键文件）。

规则：**没有 GitHub 源码链接的方案，标记为跳过（不做源码解构）**。

---

## 2. 12篇方案的 GitHub 源码可用性核验

| 序号 | 方案 | 文章链接 | GitHub源码链接 | 处理 |
|---|---|---|---|---|
| 01 | Microsoft AIOpsLab | https://zhuanlan.zhihu.com/p/1976373761038124600 | https://github.com/microsoft/AIOpsLab | 深度解析 |
| 02 | Ask Red Hat | https://zhuanlan.zhihu.com/p/1976619770745991853 | 未在正文检测到 | 跳过 |
| 03 | Gemini Cloud Assist | https://zhuanlan.zhihu.com/p/1977059222085730460 | 未在正文检测到 | 跳过 |
| 04 | IBM Instana | https://zhuanlan.zhihu.com/p/1977456614299693732 | 未在正文检测到 | 跳过 |
| 05 | Davis AI | https://zhuanlan.zhihu.com/p/1977762826962625486 | 未在正文检测到 | 跳过 |
| 06 | TrueFoundry | https://zhuanlan.zhihu.com/p/1979247270974223914 | 未在正文检测到 | 跳过 |
| 07 | DeepFlow | https://zhuanlan.zhihu.com/p/1980318597487301073 | 未在正文检测到 | 跳过 |
| 08 | Microsoft Argos | https://zhuanlan.zhihu.com/p/1981325904736192461 | 未在正文检测到 | 跳过 |
| 09 | OpenDerisk | https://zhuanlan.zhihu.com/p/1982122571202859533 | https://github.com/derisk-ai/OpenDerisk | 深度解析 |
| 10 | STRATUS | https://zhuanlan.zhihu.com/p/1987601362868011813 | 未在正文检测到 | 跳过 |
| 11 | AWS DevOps Agent | https://zhuanlan.zhihu.com/p/1988179556159485443 | 未在正文检测到 | 跳过 |
| 12 | RCAgent | https://zhuanlan.zhihu.com/p/1989415079091909901 | 未在正文检测到 | 跳过 |

---

## 3. 源码深度解析 A：AIOpsLab（microsoft/AIOpsLab）

仓库：`microsoft/AIOpsLab`

### 3.1 架构要点（从源码验证）
- 入口层：
  - `service.py`：FastAPI 服务，提供 `/problems`、`/agents`、`/simulate`。
  - `cli.py`：人类交互式命令行 Agent。
- 编排层：
  - `aiopslab/orchestrator/orchestrator.py`：统一控制代理与环境交互（ask_agent/ask_env/start_problem）。
- 问题基准层：
  - `aiopslab/orchestrator/problems/registry.py`：问题注册表，覆盖 detection/localization/analysis/mitigation 多阶段任务。
- Agent 接入层：
  - `clients/registry.py`：注册 `gpt/qwen/deepseek/vllm/openrouter/generic`。
  - `clients/generic_openai.py`：OpenAI 兼容模型接入（base_url/model/api_key 可配置）。
- 评测与会话层：
  - `assessment.py`、`aiopslab/session.py`：会话和结果保存逻辑。

### 3.2 核心优点
1. **评测导向强**：问题库结构化，天然支持基准评估。  
2. **环境闭环完整**：有故障注入、工作负载、环境动作接口。  
3. **API 化清晰**：服务端接口可用于自动化跑分。  
4. **Agent接入门槛低**：有通用 OpenAI-compatible 客户端。

### 3.3 对本项目可直接借鉴点
1. 引入 `ProblemRegistry` 思想，形成你项目的“故障样例标准库”。
2. 增加 `/simulate` 类评测接口，支持同一 incident 多模型/多参数复跑。
3. 采用 detection/localization/analysis/mitigation 四阶段标签，评测报告结构化输出。
4. 增强会话结果持久化格式，使“回放+对比”更标准化。

### 3.4 不建议直接照搬点
1. AIOpsLab偏“实验基准平台”，你项目是“生产RCA产品”，要补治理和前端可视化闭环。
2. 其多Agent协同形式相对简单，不等同于你现在的主Agent协调+专家辩论模式。

---

## 4. 源码深度解析 B：OpenDerisk（derisk-ai/OpenDerisk）

仓库：`derisk-ai/OpenDerisk`

### 4.1 架构要点（从源码验证）
- Monorepo + Workspace：
  - `pyproject.toml` 显示 workspace 成员：`derisk-app / derisk-client / derisk-core / derisk-ext / derisk-serve`。
- App 启动与服务：
  - `packages/derisk-app/src/derisk_app/derisk_server.py`：Uvicorn 启动入口。
  - `packages/derisk-app/src/derisk_app/app.py`：App 创建、路由挂载、配置加载、组件初始化。
- Agent 与执行内核：
  - `packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py`。
  - `packages/derisk-core/src/derisk/agent/expand/react_master_agent/phase_manager.py`。
- 场景与技能层（OpenRCA）：
  - `packages/derisk-ext/src/derisk_ext/agent/agents/open_rca/resource/open_rca_resource.py`。
  - `packages/derisk-ext/src/derisk_ext/agent/agents/open_rca/skills/open_rca_diagnosis/SKILL.md`。
- MCP 能力：
  - `packages/derisk-ext/src/derisk_ext/mcp/gateway.py`。
  - `packages/derisk-serve/src/derisk_serve/mcp/...`（从目录树可见完整 API/Service/Tests）。

### 4.2 核心优点
1. **工程化程度高**：模块拆分清晰，内核、扩展、服务、前端分层明确。  
2. **ReAct Master能力强**：含 doom-loop 检测、会话压缩、输出截断、phase 管理、报告生成。  
3. **技能化诊断流程**：OpenRCA 诊断 Skill 把 RCA 方法论固化为可执行规范。  
4. **MCP 网关完整**：工具协议、注册、鉴权、路由体系较完善。  
5. **场景化资源封装**：`OpenRcaSceneResource` 把场景元数据和提示拼装标准化。

### 4.3 对本项目可直接借鉴点
1. 在主Agent引入“循环保护+上下文压缩+截断策略”三件套。  
2. 将你的 RCA 流程抽成 Skill 文档 + Resource（类似 open_rca_diagnosis）。  
3. 用 PhaseManager 思想实现“探索-规划-执行-验证-报告”阶段式提示增强。  
4. 统一 MCP 网关层，把工具接入规范化（你当前已有工具雏形，需标准化）。  
5. 形成分层包结构（core/ext/serve/app）降低“上帝类”风险。

### 4.4 风险点（对你项目迁移时）
1. OpenDerisk 代码体量大，直接搬运会引入过重依赖和学习成本。  
2. 部分能力与现有前端交互模型不完全一致，需要做适配层。  
3. 强依赖其内部 `derisk-*` 包体系，建议“借鉴模式”而非“拷贝实现”。

---

## 5. 面向你项目的优化计划（基于源码而非网页摘要）

## P0（先行，1周）
1. 建“故障样例注册表 + 自动跑分脚本”（借鉴 AIOpsLab ProblemRegistry）。
2. 会话输出统一结构：阶段、证据、工具I/O、耗时、置信度。
3. 加入 “上下文压缩 + 输出截断 + 循环检测” 基础机制（借鉴 ReActMasterAgent）。

## P1（1-2周）
1. 实现 `Skill + Resource` 诊断框架：把 RCA 方法论写成可执行技能文档。
2. 阶段管理器接入主Agent（探索/规划/执行/验证/报告）。
3. 工具调用协议统一为 MCP 风格的请求/响应结构（便于前后端展示和审计）。

## P2（1-2周）
1. 代码结构重构为 `core/ext/serve/app` 四层。
2. 独立 “评测中心” + “调查工作台” 页面。
3. 增加多轮复盘对比（不同模型/提示词/参数）。

---

## 6. 本次执行结论

1. 按“网页正文中的 GitHub 源码链接”为准，12家里可做源码深挖的为 **2家**：AIOpsLab、OpenDerisk。  
2. 已完成这2家的源码级解析并给出可执行改造计划。  
3. 其余8家方案在当前文章正文未检测到源码仓库链接，已按你的规则跳过源码解析。  

---

## 7. 关键引用

- AIOpsLab 仓库：https://github.com/microsoft/AIOpsLab  
- OpenDerisk 仓库：https://github.com/derisk-ai/OpenDerisk  
- AIOpsLab README：https://raw.githubusercontent.com/microsoft/AIOpsLab/main/README.md  
- AIOpsLab Orchestrator：https://raw.githubusercontent.com/microsoft/AIOpsLab/main/aiopslab/orchestrator/orchestrator.py  
- AIOpsLab ProblemRegistry：https://raw.githubusercontent.com/microsoft/AIOpsLab/main/aiopslab/orchestrator/problems/registry.py  
- OpenDerisk README：https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/README.md  
- OpenDerisk app 启动：https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/packages/derisk-app/src/derisk_app/derisk_server.py  
- OpenDerisk app 组装：https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/packages/derisk-app/src/derisk_app/app.py  
- OpenDerisk ReActMaster：https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/packages/derisk-core/src/derisk/agent/expand/react_master_agent/react_master_agent.py  
- OpenDerisk PhaseManager：https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/packages/derisk-core/src/derisk/agent/expand/react_master_agent/phase_manager.py  
- OpenDerisk OpenRCA Skill：https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/packages/derisk-ext/src/derisk_ext/agent/agents/open_rca/skills/open_rca_diagnosis/SKILL.md  
- OpenDerisk MCP Gateway：https://raw.githubusercontent.com/derisk-ai/OpenDerisk/main/packages/derisk-ext/src/derisk_ext/mcp/gateway.py  

> OpenDerisk 专项分析文档：
> `/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-02-openderisk-source-focus-analysis.md`
