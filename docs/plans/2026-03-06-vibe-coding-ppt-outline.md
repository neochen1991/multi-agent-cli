# Vibe Coding 实战分享 PPT 大纲（业界经验主导 + 本项目案例）

更新时间：2026-03-06  
适用对象：研发负责人、SRE、平台工程、AI 工程团队  
目标：用于制作 15 页分享 PPT，重点讲清楚如何把 Vibe Coding 做成可落地的工程方法。

---

## 0. 演讲定位（建议放在讲稿首页，不单独成页）

- 主题：如何把“写得快”变成“上线稳”
- 视角：业界最佳实践 80% + 本项目实践 20%
- 听众收益：
  - 理解 Vibe Coding 的正确工程边界
  - 学会 Skill / MCP / 多 Agent 的可控接入方式
  - 拿到可执行的团队落地路线图

---

## Slide 1｜封面

**标题**：Vibe Coding 在生产级 SRE 智能体中的工程化落地  
**副标题**：从 Prompt 驱动到 Harness 驱动

**可视化建议**
- 左侧：问题现场（告警、日志、工单）
- 右侧：Agent 编排图（Main Agent + Expert Agents + Tool/MCP）

**讲解词（40s）**
- 本次分享不谈“炫技式 AI 编码”，只谈能复用、能治理、能上线的工程实践。

---

## Slide 2｜为什么 Vibe Coding 值得做

**结论句**：Vibe Coding 的价值不在“省人”，而在“缩短认知到交付的闭环”。

**要点**
- 传统开发瓶颈：上下文切换重、需求到实现链路长、跨角色协同慢。
- Vibe Coding 优势：代码生成速度提升、探索方案成本下降、迭代更快。
- 生产场景挑战：质量漂移、回归风险、审计缺失。

**可视化建议**
- 左右对比图：传统流程 vs Agent 协作流程

**讲解词（50s）**
- 强调“快”只是起点；没有约束与验证，速度会放大错误。

---

## Slide 3｜业界共识 1：Harness Engineering 是核心

**结论句**：生产可用性的上限由 Harness 决定，而不是由单次 Prompt 决定。

**要点**
- OpenAI 提倡把精力放在 harness：任务拆解、校验、反馈闭环。
- 关键思想：让模型做推理，让系统做控制（状态机、验证、回退、门禁）。
- 结果导向：可重复、可评估、可迭代，而非一次性“灵感成功”。

**可视化建议**
- 金字塔：Prompt 在顶层，Harness 在底座

**讲解词（60s）**
- 解释为什么团队要先建“轨道”再追求“更强模型”。

---

## Slide 4｜业界共识 2：上下文工程优先于长 Prompt

**结论句**：高质量上下文组织，比堆砌超长提示词更有效。

**要点**
- Anthropic / OpenAI 都强调：清晰任务边界、结构化输入、分步链路。
- GitHub Copilot / Cursor 实践：规则文件、代码索引、局部上下文注入。
- 实用原则：只给当前步骤需要的信息，减少噪声上下文。

**可视化建议**
- 漏斗图：原始信息 -> 清洗 -> 任务相关上下文 -> 模型输入

**讲解词（50s）**
- 引出“Skill/MCP 本质是上下文工程基础设施”。

---

## Slide 5｜业界共识 3：标准工作流替代“即兴开发”

**结论句**：稳定团队都采用固定节奏：Explore -> Plan -> Build -> Verify -> Release。

**要点**
- 先理解问题和约束，再动代码。
- 每个阶段都有退出条件（DoD），避免“写到哪算哪”。
- 自动化验证必须前置到提交前与 CI 阶段。

**可视化建议**
- 五阶段流程图 + 每阶段产物（文档、代码、测试、报告）

**讲解词（55s）**
- 强调“流程不是为了慢，而是为了减少返工”。

---

## Slide 6｜业界共识 4：测试和评测是 Vibe Coding 的刹车系统

**结论句**：没有评测门禁，Vibe Coding 在生产环境不可控。

**要点**
- 单测/集成测试保障局部正确性。
- Benchmark/Eval 保障策略正确性（命中率、超时率、失败率）。
- CI Gate 保障团队协作一致性，避免回归悄悄进入主干。

**可视化建议**
- 质量门禁泳道图：本地 -> PR -> CI -> 发布

**讲解词（50s）**
- 给出实践建议：从 3 个核心指标起步，不追求一步到位。

---

## Slide 7｜业界共识 5：MCP/工具化接入必须标准化

**结论句**：Agent 能力扩展要靠标准协议，不靠临时脚本拼接。

**要点**
- MCP 提供模型与外部资源/工具的统一接口思路。
- 工具调用必须具备：权限边界、开关控制、超时、审计。
- 安全基线：最小权限、可追踪、可回滚。

**可视化建议**
- 三层图：Agent 层 -> MCP/Tool Gateway -> 数据源层（日志/代码库/DB/APM）

**讲解词（55s）**
- 说明“可接入”与“可治理”必须同时成立。

---

## Slide 8｜业界共识 6：多 Agent 不是多线程，而是可控协作机制

**结论句**：多 Agent 的关键不在数量，在协作协议和收敛机制。

**要点**
- 推荐模式：Commander/Supervisor + Specialist + Judge。
- 协作要件：任务分配协议、证据交换协议、停止条件。
- LangGraph 等框架价值：状态流转、路由、并行与恢复能力。

**可视化建议**
- Hub-and-Spoke 结构图：Main Agent 居中，专家 Agent 环绕

**讲解词（60s）**
- 强调避免“伪多 Agent”（每个 agent 各说各话，不收敛）。

---

## Slide 9｜业界反模式（必须避开）

**结论句**：多数失败案例不是模型不够强，而是工程纪律缺失。

**要点**
- 反模式 1：Accept All 自动改代码，无验证直接合并。
- 反模式 2：上下文无限堆砌，导致模型漂移与幻觉。
- 反模式 3：工具调用无权限与审计，难以追责。
- 反模式 4：超时和异常无终态，任务长期 pending。

**可视化建议**
- 反模式雷达图 + 对应治理措施

**讲解词（45s）**
- 给听众明确“哪些坑最容易踩”。

---

## Slide 10｜本项目案例 1：我们如何实现 Harness 化

**结论句**：本项目把“模型推理”和“系统控制”做了明确分层。

**项目映射（代码层）**
- Runtime 编排：`backend/app/runtime/langgraph_runtime.py`
- Graph 构建：`backend/app/runtime/langgraph/builder.py`
- Agent 节点执行：`backend/app/runtime/langgraph/nodes/agents.py`
- 路由与监督：`backend/app/runtime/langgraph/nodes/supervisor.py`

**机制要点**
- 主 Agent 命令先行（先发命令，再专家执行）。
- 统一事件流回放（WebSocket 实时 + 历史查询）。
- 终态保障（失败也必须可见、可解释）。

**可视化建议**
- 简化时序图：用户 -> 主 Agent -> 专家 Agent -> 裁决 -> 报告

**讲解词（60s）**
- 说明这是“从 demo 到生产”的关键分水岭。

---

## Slide 11｜本项目案例 2：Skill + Tool + 审计闭环

**结论句**：工具调用不是“能调就行”，而是“可控、可审、可解释”。

**项目映射（代码层）**
- 工具上下文与门禁：`backend/app/services/agent_tool_context_service.py`
- Skill 路由：`backend/app/services/agent_skill_service.py`
- 配置持久化：`backend/app/repositories/tooling_repository.py`

**机制要点**
- 命令门禁（`use_tool` + 策略开关）。
- Skill 命中（`skill_hints` + 触发词匹配）。
- 工具 I/O 审计（请求摘要、返回摘要、状态、耗时）。

**可视化建议**
- 调用链图：Command -> Gate -> Tool -> Skill -> LLM -> Audit

**讲解词（60s）**
- 强调“前端可视化 + 后端日志”双重可追踪。

---

## Slide 12｜本项目案例 3：韧性设计（超时、降级、恢复）

**结论句**：生产场景下，系统最重要的能力是“失败时仍可推进”。

**机制要点**
- 超时重试与预算控制（不同 agent 可配置）。
- Prompt 压缩与局部降级，避免整会话阻塞。
- 断点续写：中断后可恢复会话上下文与阶段状态。

**可视化建议**
- 状态机图：RUNNING -> RETRY -> DEGRADED -> COMPLETED/FAILED

**讲解词（55s）**
- 说明为什么“无响应”会严重破坏用户信任。

---

## Slide 13｜团队落地模板（2 周可执行）

**结论句**：先统一方法，再扩展能力；先可用，再高级。

**Week 1**
- 定义 AGENTS.md（约束与导航）
- 梳理统一工作流（Explore/Plan/Build/Verify）
- 接入最小测试与 CI 门禁

**Week 2**
- 增加工具调用审计
- 增加超时降级与终态保证
- 增加基础 benchmark 并纳入发布门禁

**可视化建议**
- 甘特图 / 看板图（任务 -> 负责人 -> 验收标准）

**讲解词（45s）**
- 给团队“照着就能做”的起步路径。

---

## Slide 14｜90 天路线图（从可用到规模化）

**结论句**：Vibe Coding 要变成组织能力，必须走平台化治理路线。

**阶段目标**
- P0：可用性（不 pending、可观测、可回放）
- P1：准确性（Top-K 根因、跨源证据校验）
- P2：可控自治（审批、回滚、No-Regression Gate）
- P3：持续学习（反馈闭环、A/B 评测、策略演进）

**可视化建议**
- 四阶段路线图（能力成熟度模型）

**讲解词（55s）**
- 把短期效率和长期治理统一起来。

---

## Slide 15｜结尾与行动清单

**结论句**：Vibe Coding 的终局不是“自动写代码”，而是“可控地持续交付正确结果”。

**行动清单（本周）**
- 1. 固化 AGENTS.md 与工程约束
- 2. 给关键链路加可观测事件和审计
- 3. 建立最小 benchmark 并加 CI 门禁
- 4. 把工具接入改为开关化、可回滚
- 5. 用一次真实故障做端到端演练并复盘

**可视化建议**
- Checklist 卡片 + “下周复盘指标”

**讲解词（40s）**
- 鼓励团队从一个真实场景开始，先跑通闭环，再扩展能力。

---

## 附录 A｜可直接复用的演讲主线（1 分钟版）

1. Vibe Coding 确实快，但只快不稳会放大线上风险。  
2. 业界成熟做法是 Harness Engineering：模型负责推理，系统负责控制。  
3. Skill/MCP/多 Agent 不是功能堆叠，而是上下文、能力和治理的标准化。  
4. 本项目验证了这条路线：命令先行、工具门禁、审计闭环、韧性恢复。  
5. 下一步要做的是把方法固化为团队工程标准与 CI 门禁。

---

## 附录 B｜参考资料（建议页脚引用）

1. OpenAI, Harness Engineering  
   https://openai.com/index/harness-engineering/
2. OpenAI, Prompt Engineering Guide  
   https://platform.openai.com/docs/guides/prompt-engineering
3. Anthropic, Claude Code Best Practices  
   https://www.anthropic.com/engineering/claude-code-best-practices
4. Anthropic Docs, Prompt Engineering（Clear/Direct, Chain）  
   https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct  
   https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/chain-prompts
5. GitHub Copilot Best Practices  
   https://docs.github.com/en/copilot/get-started/best-practices
6. Cursor Rules / Context  
   https://docs.cursor.com/context/rules
7. LangGraph Workflows & Agents  
   https://docs.langchain.com/oss/python/langgraph/workflows-agents
8. Model Context Protocol（Overview + Spec + Security）  
   https://modelcontextprotocol.io/  
   https://modelcontextprotocol.io/specification/2024-11-05/architecture/index  
   https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
9. Thoughtworks（生产级 Vibe Coding 讨论）  
   https://www.thoughtworks.com/en-us/insights/blog/generative-ai/can-vibe-coding-produce-production-grade-software
10. Sourcegraph Cody Agentic Chat（上下文检索实践）  
   https://sourcegraph.com/docs/cody/capabilities/agentic-chat

---

## 附录 C｜本项目引用点（用于“20% 项目经验”页）

- 入口文档：`AGENTS.md`、`README.md`
- 代码全景：`docs/wiki/code-wiki.md`
- 核心运行时：
  - `backend/app/runtime/langgraph_runtime.py`
  - `backend/app/runtime/langgraph/builder.py`
  - `backend/app/runtime/langgraph/nodes/agents.py`
  - `backend/app/runtime/langgraph/nodes/supervisor.py`
  - `backend/app/runtime/langgraph/execution.py`
- 工具与 Skill：
  - `backend/app/services/agent_tool_context_service.py`
  - `backend/app/services/agent_skill_service.py`
  - `backend/app/repositories/tooling_repository.py`

