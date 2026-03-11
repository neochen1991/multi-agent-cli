# Standard / Quick 模式重定义设计

## 背景

当前系统中的 `standard / quick / background / async` 同时混合了承载两类语义：

1. 分析能力策略
2. 执行方式

这导致用户理解和运行时实现都存在偏差：

- `quick` 目前更像“低成本/快收敛”的混合模式，但还不足够明确地面向“弱模型、低并发、易超时”场景。
- `standard` 目前是默认模式，但没有被明确建模成“适用于强模型、高并发、深度分析”的完整策略。
- `background` 当前既承担“后台执行方式”，又在 runtime policy 中影响专家集合和 phase mode，语义过重。

用户最新要求是：

- `standard` 应用于能力强、并发高的 LLM 大模型，支持深度、多轮次根因分析。
- `quick` 应适配能力稍弱、并发很小的 LLM 服务，避免大量子 Agent 调用导致超时。
- 用户自己选择模式，不做自动切换。

## 目标

本次重构把模式语义收敛为：

- `standard`：完整分析策略
- `quick`：受限模型友好策略
- `background`：执行方式，而不是能力等级

并保证：

1. 用户能清楚理解两种能力策略的差异。
2. `quick` 明显减少 LLM 压力，降低 timeout 概率。
3. `standard` 能承载多轮次、深模式、跨专家协作。
4. 现有 `background` 保持兼容，但不再单独决定分析能力等级。

## 新语义定义

### 1. Standard

面向：

- 能力强的 LLM
- 并发高、稳定性好的模型服务

目标：

- 输出更完整的根因链
- 支持多源证据、替代根因排除、验证计划

策略特征：

- 更完整的专家集合
- 支持 collaboration / critique / verification
- 更高 timeout / queue / token 预算
- 深模式下允许更长回合和更多收口条件

### 2. Quick

面向：

- 能力稍弱的 LLM
- 并发很小、容易排队和超时的模型服务

目标：

- 以更少调用次数拿到“足够可信”的结论
- 避免子 Agent timeout 造成整局降级或失败

策略特征：

- 更小的专家集合
- 默认关闭 collaboration / critique
- 更小 prompt、更少 token、更低首轮 fan-out
- 更少 LLM 总调用次数
- 允许保守但可用的中等置信收口

### 3. Background

定义：

- 仅表示“后台持续执行”的运行方式

约束：

- 不再被当成第三种能力策略
- 它应与 `standard/quick` 的策略解耦

备注：

- 本轮为降低改动面，先保持兼容实现；后续可考虑拆成 `execution_mode + execution_delivery` 双字段。

## 设计方案

### 方案 A：推荐

重定义 `standard/quick` 为两套正式策略，`background` 仅保留执行语义。

优点：

- 语义最清楚
- 直接对齐用户的模型能力分层需求
- 后续可继续扩展 provider profile，而不污染 mode

缺点：

- 需要调整 runtime policy / budgeting / 文案 / 部分测试

### 方案 B：只调参数，不改语义

优点：

- 改动小

缺点：

- 用户仍然会混淆“分析能力模式”和“执行方式”
- `background` 仍是半策略半执行语义

### 方案 C：引入 mode + profile 双层模型

优点：

- 长期最灵活

缺点：

- 本轮复杂度过高，不适合作为当前修复

## 本轮实施范围

1. 重构 runtime policy
2. 重构 budgeting/timeout/queue 规则
3. 调整前端模式文案
4. 补 quick/standard 行为回归测试

## 非目标

本轮不做：

- 后端 API 删除 `background/async`
- 自动根据 provider 切模式
- 引入新的数据库配置结构
- 重做 deployment profile 中心

## 验收标准

1. `standard` 模式下，policy 明确允许更完整专家集与更深协作链路。
2. `quick` 模式下，policy 明确减少专家数、讨论步数和 LLM 压力。
3. `quick` 模式相关测试证明其比 `standard` 更不容易触发 timeout 路径。
4. 前端对用户的模式说明与后端策略一致。
