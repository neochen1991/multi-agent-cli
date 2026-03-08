# PostgreSQL 业务表信息

## 库与 Schema
- database: order_center
- schema: public
- owner: order-sre

## 业务表
### public.t_order
- 说明: 订单主表，记录订单状态与金额。
- 关键字段: order_no, user_id, order_status, total_amount, created_at
- 索引: uk_t_order_order_no, idx_t_order_status

### public.t_order_item
- 说明: 订单明细表。
- 关键字段: order_no, sku_code, quantity, sale_price
- 索引: idx_t_order_item_order_no, idx_t_order_item_sku

### public.t_inventory
- 说明: 库存表，下单时会对热点 SKU 执行 `for update`。
- 关键字段: sku_code, available_stock, locked_stock, updated_at
- 索引: uk_t_inventory_sku_code
- 风险点: 热门 SKU 会触发行锁竞争。

### public.t_payment_record
- 说明: 支付预占记录表。
- 关键字段: order_no, payment_status, retry_count, updated_at
- 索引: idx_t_payment_record_order_no, idx_t_payment_record_status

## 诊断信号
- `slow_sql`: 慢 SQL 明细
- `top_sql`: 高频 SQL 明细
- `session_status`: 活跃/等待会话状态
- `lock_waits`: 锁等待明细

## 事故指向
- 热点 SQL: `select available_stock from t_inventory where sku_code = ? for update`
- 现象链: inventory 锁等待 -> order 事务拉长 -> Hikari pending 增长 -> order 500 激增
