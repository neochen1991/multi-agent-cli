# 单仓多服务 Mock E2E 场景设计

**目标**

构造一套足够接近真实业务事故现场的本地模拟数据，供当前多 Agent 系统执行端到端排障分析。场景采用单仓多服务模式，在同一个本地 Git 仓库中同时包含 `order-service`、`inventory-service`、`payment-service` 三个服务模块，并配套日志、责任田、数据库快照、指标材料与变更历史。

**核心约束**

1. 数据必须互相一致，不能出现代码、日志、责任田、数据库表、指标名称互相对不上的情况。
2. 数据必须可被当前系统真实消费，而不是只做展示文档。
3. 不引入额外后端逻辑改造，优先复用现有工具读取路径：
   - `CodeAgent` 读取本地 Git 仓库
   - `LogAgent` 读取本地日志文件
   - `DomainAgent` 读取责任田 CSV
   - `DatabaseAgent` 读取 SQLite 快照
   - `MetricsAgent` 从 incident/log 文本中抽取指标信号
4. 场景要体现真实的上下游联动，而不是单点报错。

**推荐事故主线**

- 主入口：`POST /api/v1/orders`
- 表象：`order-service` 大量返回 500，接口耗时飙升，连接池打满
- 深层诱因：`inventory-service` 热点 SKU 行锁竞争，导致订单事务持锁时间拉长
- 次级放大：`payment-service` 预占调用超时重试，进一步拉长请求生命周期

**数据设计**

## 1. 单仓多服务代码结构

在一个 monorepo 下构造：
- `services/order-service`
- `services/inventory-service`
- `services/payment-service`
- `docs/change-notes`
- `sql/`

代码中要明确体现：
- `order-service` 调用库存与支付
- `inventory-service` 执行热点库存锁 SQL
- `payment-service` 执行预占与重试逻辑
- 配置中出现连接池参数和超时阈值

## 2. 日志设计

日志必须包含完整时间窗：
- 正常期
- 预热异常期
- 峰值故障期
- 恢复前观察期

日志字段至少包含：
- `timestamp`
- `service`
- `traceId`
- `orderNo`
- `skuCode`
- `api`
- `dependency`
- `sql/table`
- 指标片段：`error_rate / latency / hikari_pending / db_conn / threads / cpu`

## 3. 责任田设计

至少 3 条责任田资产：
- 订单提交
- 库存扣减
- 支付预占

每条都带：
- `feature`
- `domain`
- `aggregate`
- `api_interfaces`
- `code_items`
- `database_tables`
- `dependency_services`
- `monitor_items`
- `owner_team`
- `owner`

## 4. 数据库设计

继续使用 SQLite 快照供 `DatabaseAgent` 真实读取。

至少包含：
- 业务表：`t_order`、`t_order_item`、`t_inventory`、`t_payment_record`
- 诊断表：`slow_sql`、`top_sql`、`session_status`、`lock_waits`

要求：
- 表结构与责任田字段对得上
- 慢 SQL 和锁等待能指向库存热点锁问题
- 会话状态能反映连接池/数据库活跃会话打满

## 5. 指标材料设计

当前 `MetricsAgent` 不直接读本地 Markdown 文档，因此指标要双轨提供：
- 一份给人看的指标参考文档
- 一份嵌入日志/incident 文本里的关键指标信号，供当前实现抽取

指标至少包括：
- `order.error.rate`
- `order.latency.p99`
- `inventory.lock.wait.p95`
- `payment.timeout.rate`
- `hikari.pending.connections`
- `db.active.connections`
- `jvm.thread.count`
- `process.cpu.usage`

**预期效果**

- `CodeAgent` 能在单仓中跨模块搜到下单 -> 库存 -> 支付的调用链
- `LogAgent` 能从连续日志里重建异常时间线
- `DomainAgent` 能从责任田看出三个业务模块的边界与依赖
- `DatabaseAgent` 能查到热点表、慢 SQL、锁等待、会话状态
- `MetricsAgent` 能抓到异常窗口并辅助判断放大链路

**非目标**

- 这一步不直接跑 incident
- 这一步不修改系统执行逻辑
- 这一步不引入真实 Postgres 或 Prometheus 服务
