# 2026-03-02 生产RCA系统统一实施计划（整合版）

> 方案整合来源：
> - `/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-01-production-rca-execution-checklist.md`
> - `/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-02-agenticops-12-schemes-improvement-plan.md`
> - `/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-02-12-company-reading-comparison-and-optimization-plan.md`
> - `/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-02-12-company-github-source-deep-dive.md`
> - `/Users/neochen/multi-agent-cli_v2/docs/plans/2026-03-02-openderisk-source-focus-analysis.md`

> 约束：不引入外部数据库，仅本地文件/内存存储。

---

## 1. 目标与策略

## 1.1 总目标
把当前系统从“可用的多Agent分析工具”升级为“可评估、可治理、可扩展、可持续优化的生产RCA平台”。

## 1.2 实施策略
1. 以现有已完成能力为基线，做增量改造，不推倒重来。  
2. 先做质量与稳定性，再做扩展与自治。  
3. 参考 OpenDerisk/AIOpsLab 的“机制层能力”，避免直接复制大体量实现。  

---

## 2. 当前基线（已完成）

来自既有执行清单，以下能力可视为已落地基座：
1. 事件去重、LLM日志规范化、失败重试、无结论报告拦截。  
2. 编排器拆分初步完成，状态模型收敛与并行执行已有基础。  
3. 前端核心体验已改善（三页分工、卡片化、北京时间一致）。  
4. 冒烟/E2E 回归脚本与样本集、SLO指标基础已建立。  

说明：本计划聚焦“下一阶段增量能力”。

---

## 3. 统一增量计划（P0-P4）

## P0（1周）：评测与运行时可追溯增强

目标：把“可运行”升级为“可量化评估 + 可复盘追责”。

- [x] `P0-1` 建立统一 benchmark harness（故障样例->评分报告）。  
- [x] `P0-2` 增加执行谱系产物（session级 JSON：阶段、Agent、工具、证据、耗时、置信度）。  
- [x] `P0-3` 增加失败会话一键回放（按时间线重放关键节点）。  
- [x] `P0-4` 增加质量基线看板数据文件（Top1/Top3、失败率、超时率、空结论率）。  

交付物：
- `backend/app/benchmark/`  
- `backend/app/runtime/trace_lineage/`  
- `docs/metrics/baseline-*.json`

验收：
1. 一条命令输出 benchmark 结果。  
2. 任意失败会话可从 lineage 文件重放关键流程。  

---

## P1（1-2周）：推理质量与证据治理

目标：把“文本辩论”升级为“证据驱动辩论”。

- [x] `P1-1` 统一证据对象模型：`Evidence/Claim/Hypothesis`。  
- [x] `P1-2` Judge 强制跨源引用（日志+代码/领域至少2源）。  
- [x] `P1-3` 引入因果评分层（相关性分与因果性分分离）。  
- [x] `P1-4` 引入关键Agent自一致性投票（N次低成本轨迹汇总）。  
- [x] `P1-5` 新增“规则建议Agent”（阈值/窗口/触发条件草案）。  

交付物：
- `backend/app/runtime/evidence/`  
- `backend/app/runtime/judgement/causal_score.py`  
- `backend/app/runtime/agents/rule_suggestion_agent.py`

验收：
1. 报告每条核心结论都有可点击证据引用。  
2. “需要进一步分析”占比明显下降。  

---

## P2（1-2周）：工具/MCP平台化与安全治理

目标：把“工具能用”升级为“工具可治理、可审计、可扩展”。

- [x] `P2-1` MCP工具注册中心（schema/超时/权限/审计级别）。  
- [x] `P2-2` 连接器协议统一：`Repo/Telemetry/Asset/Ticket`。  
- [x] `P2-3` 工具安全网（命令白名单、路径白名单、参数脱敏、输出截断）。  
- [x] `P2-4` 工具调用审计前端可视化（输入摘要+返回摘要+耗时+状态）。  
- [x] `P2-5` 工具开关策略细化（按Agent/场景/命令动态启停）。  

交付物：
- `backend/app/runtime/tool_registry/`  
- `backend/app/runtime/connectors/`  
- `frontend/src/pages/ToolsCenter/`

验收：
1. 新增工具无需改核心编排即可接入。  
2. 每次工具调用都有完整审计记录。  

---

## P3（1-2周）：主Agent协同与抗失控机制（重点借鉴 OpenDerisk）

目标：让多Agent协同“更像团队工作”，并可持续稳定运行。

- [x] `P3-1` 主Agent阶段管理（探索->规划->执行->验证->报告）。  
- [x] `P3-2` 引入循环保护（Doom Loop Detector）。  
- [x] `P3-3` 引入上下文压缩与历史修剪（SessionCompaction + Pruning）。  
- [x] `P3-4` 引入大输出截断机制（避免上下文污染和超时）。  
- [x] `P3-5` 引入任务看板（可选）用于多轮讨论收敛控制。  

交付物：
- `backend/app/runtime/langgraph/phase_manager.py`  
- `backend/app/runtime/langgraph/doom_loop_guard.py`  
- `backend/app/runtime/langgraph/session_compaction.py`  
- `backend/app/runtime/langgraph/output_truncation.py`

验收：
1. 主Agent不会出现持续循环提问失控。  
2. 长会话超时率显著下降。  

---

## P4（2周）：产品化体验与反馈学习闭环

目标：形成“调查->结论->复核->优化”的完整闭环。

- [x] `P4-1` 调查工作台（时间线 + 证据链图谱 + 决策摘要）。  
- [x] `P4-2` 评测中心（版本维度准确率/耗时趋势）。  
- [x] `P4-3` 治理中心（成本估算、配额、审计检索、系统边界卡）。  
- [x] `P4-4` 用户反馈闭环（采纳/驳回/修订 -> 提示词/规则优化候选）。  
- [x] `P4-5` 报告导出与对比（同故障多次分析横向对比）。  

交付物：
- `frontend/src/pages/InvestigationWorkbench/`  
- `frontend/src/pages/BenchmarkCenter/`  
- `frontend/src/pages/GovernanceCenter/`  
- `backend/app/governance/system_card.py`

验收：
1. 用户可在单页完成调查和结论确认。  
2. 版本间质量趋势可量化查看。  

---

## 4. 里程碑与节奏（建议）

1. M1（第1周）：完成 P0。  
2. M2（第2-3周）：完成 P1。  
3. M3（第4-5周）：完成 P2。  
4. M4（第6周）：完成 P3。  
5. M5（第7-8周）：完成 P4。  

---

## 5. 执行顺序与依赖

1. 必须先完成：P0 -> P1。  
2. P2 与 P3 可并行推进，但 P3 依赖 P1 的证据模型。  
3. P4 依赖 P0-P3 的数据与事件标准化。  

---

## 6. 风险与应对

1. 风险：改造期引入行为回归。  
应对：每个阶段保留 feature flag，默认可回退。

2. 风险：上下文压缩影响结论准确性。  
应对：压缩前后 A/B 对比，并设置最小保留消息窗口。

3. 风险：工具能力提升后引入安全暴露。  
应对：白名单 + 脱敏 + 调用审计强制开启。

4. 风险：前端复杂度再次上升。  
应对：页面按域拆分，UI协议（消息卡片类型）稳定化。

---

## 7. 统一验收口径（DoD）

满足以下条件视为本计划完成：
1. 同一故障可重复分析并产出可对比结果。  
2. 报告结论均有证据链可追溯。  
3. 工具调用全链路可审计且可在前端查看。  
4. 长会话下无明显循环失控，超时率可控。  
5. 具备调查工作台、评测中心、治理中心三类产品化页面。  

---

## 8. 立即执行建议（本周）

1. 先启动 P0-1、P0-2（benchmark 与 lineage）。  
2. 同步设计 P1 的 `Evidence/Claim` 数据结构（避免后续返工）。  
3. 预埋 P3 所需的 `phase` 与 `loop_guard` 事件字段（降低改造成本）。
