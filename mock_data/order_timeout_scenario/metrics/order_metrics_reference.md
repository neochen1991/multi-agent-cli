# Order Platform 指标参考

## 指标口径
- order.error.rate: 订单提交错误率，阈值 5%
- order.latency.p99: 订单提交 P99，阈值 2s
- inventory.lock.wait.p95: 库存锁等待 P95，阈值 500ms
- payment.timeout.rate: 支付预占超时率，阈值 2%
- hikari.pending.connections: Hikari 等待连接数，阈值 10
- db.active.connections: 数据库活跃连接数，阈值 18/20
- jvm.thread.count: JVM 线程数，阈值 220
- process.cpu.usage: CPU 使用率，阈值 85%

## 事故解读
- inventory.lock.wait.p95 与 db.active.connections 同时抬升时，优先排查热点库存锁。
- payment.timeout.rate 上升会放大订单请求生命周期，但不是主根因。
- order.error.rate、order.latency.p99 与 hikari.pending.connections 同步抬升时，通常代表连接池耗尽已经成为用户侧故障表象。
