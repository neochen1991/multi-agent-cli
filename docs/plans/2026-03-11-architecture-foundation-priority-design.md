# Architecture Foundation Priority Design

**Goal**

在不推翻当前 LangGraph 运行时的前提下，优先补强项目的三项底座能力：
- 结构化状态单一权威化
- 子图/阶段边界硬化
- 证据图最小落地

这样后续再继续做深度分析、工具闭环、治理门控时，不会建立在继续膨胀的 orchestrator 和多套并行语义上。

---

## 1. 当前实现判断

当前项目已经具备比较完整的工程化基础：

- 有 typed state + reducer
- 有动态图构建
- 有 route guardrail / fallback / human review / report
- 有 `agent_local_state`、context envelope、smoke/fixture、治理统计

但从架构角度看，仍有三个长期风险：

1. 状态权威源仍不够单一
   - `structured state` 与兼容 flat 字段并存
   - 很多运行时路径依然会先 flatten，再混入局部结果，再重新快照
   - 一旦未来再扩字段，极易出现“某条路径读的是旧语义，另一条路径写的是新语义”

2. 编排逻辑仍偏中心化
   - `builder.py` 已经清晰，但复杂行为仍大量收束在 `langgraph_runtime.py` 和 `execution.py`
   - judgment / report / human review 等边界还不是足够独立的模块

3. 证据结构仍偏线性列表
   - 当前有 `evidence_chain`、`top_k_hypotheses`
   - 但还缺 claims 与 supports / contradicts / missing_checks 的稳定图结构
   - 导致深模式、benchmark、治理评测都还要靠 prompt 语义而不是结构化关系

---

## 2. 设计目标

本轮不追求“重写整套 runtime”，而是做最小但方向正确的底座升级：

1. 让结构化 state 成为唯一权威写路径
2. 把 judgment / review 的关键边界从 runtime 大类中收紧出来
3. 在保持现有接口兼容的前提下，给最终结论补最小 claim graph

约束：

- 不破坏当前前端结果展示和 report 输出
- 不推翻当前 smoke/fixture 协议
- 不扩大 tool loop 范围，只补架构基础
- 新增关键代码必须有中文注释

---

## 3. 方案比较

### 方案 A：状态优先，渐进式拆边界，最后补证据图

做法：
- 先统一 state 写路径
- 再抽 judgment/review 边界 helper
- 最后给 final payload / result / report 增加 claim graph 字段

优点：
- 风险最低
- 现有 smoke 和前端最容易保持稳定
- 后续能力建设都能复用

缺点：
- 前两步用户体感提升不如“直接增强 agent”明显

### 方案 B：先做证据图，再回头收状态

优点：
- 最快改善结论可解释性

缺点：
- 如果 state 还不单一，claim graph 很容易又长成另一套并行字段

### 方案 C：先大规模子图化

优点：
- 架构形态最“漂亮”

缺点：
- 改动面大
- 对当前活跃迭代仓库回归风险最高

**推荐：方案 A**

原因：
- 最符合当前仓库状态
- 能让后续分析能力与治理能力的投入不返工

---

## 4. 目标架构

### 4.1 状态层

保留当前 `phase_state / routing_state / output_state / context_state` 分层。

要求：
- 所有节点/服务对 state 的写入统一通过结构化同步 helper
- flat 字段只作为兼容读视图，不再作为真实写目标
- state snapshot 必须从结构化 state 反推 flat view，而不是反过来

### 4.2 编排层

保留当前主图骨架：

`init -> round_start -> supervisor -> analysis/judgment -> round_evaluate -> finalize`

但收紧两类边界：

- `judgment boundary`
  - Judge 输入整理
  - Judge 输出标准化
  - final payload 生成

- `review boundary`
  - HITL pending/review/resume 的状态整理
  - 与主运行时解耦

### 4.3 证据层

在现有 `final_judgment` 下新增最小结构：

- `claims`
- `supports`
- `contradicts`
- `missing_checks`
- `eliminated_alternatives`

兼容策略：
- 现有 `evidence_chain` 继续保留
- claim graph 先作为附加结构，不要求前端立即消费
- result/report 先只抽取高价值字段

---

## 5. 实施范围

### 第一阶段：状态单一化

文件：
- `backend/app/runtime/langgraph/state.py`
- `backend/app/runtime/langgraph/services/state_transition_service.py`
- `backend/app/runtime/langgraph_runtime.py`

目标：
- 收敛剩余双写路径
- 补 state 权威化测试

### 第二阶段：子图边界硬化

文件：
- `backend/app/runtime/langgraph/builder.py`
- `backend/app/runtime/langgraph/execution.py`
- `backend/app/runtime/langgraph_runtime.py`

目标：
- 抽出 judgment / review 边界 helper
- 减少 runtime 主类继续膨胀

### 第三阶段：证据图最小落地

文件：
- `backend/app/runtime/langgraph_runtime.py`
- `backend/app/services/debate_service.py`
- `backend/app/services/report_generation_service.py`

目标：
- 增加 claim graph 字段
- 保持 result/report 向后兼容

---

## 6. 验收标准

1. state 相关回归通过，且不再依赖 legacy flat merge 顺序
2. judgment/report 层 `confidence` 继续保持统一
3. `order-404-route-miss` 与 `payment-timeout-upstream` smoke 继续通过
4. final payload 中存在最小 claim graph 结构，且不破坏现有前端展示

---

## 7. 风险与控制

风险：
- state 权威化改动容易引入隐蔽回归
- final payload 增字段可能影响旧的结果消费逻辑

控制：
- 先写失败测试再改代码
- claim graph 只增不删
- 先跑 targeted tests，再跑 smoke

