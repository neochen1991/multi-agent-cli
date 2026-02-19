---
{
  "type": "operations_case_library",
  "version": "1.0",
  "cases": [
    {
      "id": "OPS-ORDER-001",
      "title": "下单接口 NPE 导致订单创建失败",
      "description": "POST /api/v1/orders 返回 500，日志出现 NullPointerException。",
      "incident_type": "application_error",
      "domain": "order",
      "aggregate": "OrderAggregate",
      "api_endpoint": "POST /api/v1/orders",
      "symptoms": ["下单失败", "订单创建失败", "HTTP 500"],
      "log_signatures": ["NullPointerException", "OrderAppService#createOrder", "OrderAggregate#placeOrder"],
      "root_cause": "请求 DTO 中 items 为空，未在应用层做前置校验。",
      "root_cause_category": "null_pointer",
      "solution": "在 OrderAppService 增加参数校验并在聚合根构造函数中强化不变式检查。",
      "fix_steps": [
        "在 OrderAppService#createOrder 校验 items 非空",
        "在 OrderAggregate#placeOrder 增加业务断言",
        "补充单测覆盖空订单项场景"
      ],
      "related_services": ["order-service"],
      "related_code": [
        "OrderController#createOrder",
        "OrderAppService#createOrder",
        "OrderAggregate#placeOrder"
      ],
      "related_tables": ["t_order", "t_order_item"],
      "tags": ["order", "npe", "create-order"]
    },
    {
      "id": "OPS-PAYMENT-001",
      "title": "支付确认接口重复回调导致状态冲突",
      "description": "POST /api/v1/payments/confirm 多次回调，部分订单状态异常。",
      "incident_type": "integration_error",
      "domain": "payment",
      "aggregate": "PaymentAggregate",
      "api_endpoint": "POST /api/v1/payments/confirm",
      "symptoms": ["支付确认失败", "重复回调", "订单支付状态异常"],
      "log_signatures": ["DuplicatePaymentCallbackException", "PaymentAppService#confirm"],
      "root_cause": "支付回调幂等键设计不完整，导致重复确认写入。",
      "root_cause_category": "idempotency",
      "solution": "按 paymentId + channelTxNo 增加唯一约束，并在应用层做幂等校验。",
      "fix_steps": [
        "新增幂等索引",
        "补充 PaymentAppService 幂等分支",
        "增加回放压测场景"
      ],
      "related_services": ["payment-service", "order-service"],
      "related_code": [
        "PaymentController#confirmPayment",
        "PaymentAppService#confirm",
        "PaymentAggregate#confirm"
      ],
      "related_tables": ["t_payment", "t_payment_attempt"],
      "tags": ["payment", "idempotency", "callback"]
    },
    {
      "id": "OPS-INVENTORY-001",
      "title": "库存预占接口超时导致下单失败",
      "description": "POST /api/v1/inventory/reservations 超时，订单流转中断。",
      "incident_type": "timeout",
      "domain": "inventory",
      "aggregate": "InventoryAggregate",
      "api_endpoint": "POST /api/v1/inventory/reservations",
      "symptoms": ["库存预占失败", "下单超时", "库存服务响应慢"],
      "log_signatures": ["TimeoutException", "InventoryReservationAppService#reserve"],
      "root_cause": "库存表热点行锁竞争严重，导致事务等待超时。",
      "root_cause_category": "db_lock_contention",
      "solution": "按仓库维度拆分库存记录并引入异步预占队列削峰。",
      "fix_steps": [
        "增加索引与分片键",
        "引入预占异步队列",
        "增加锁等待告警阈值"
      ],
      "related_services": ["inventory-service", "order-service"],
      "related_code": [
        "InventoryReservationController#createReservation",
        "InventoryReservationAppService#reserve",
        "InventoryAggregate#reserve"
      ],
      "related_tables": ["t_inventory", "t_inventory_reservation", "t_inventory_txn_log"],
      "tags": ["inventory", "timeout", "db-lock"]
    }
  ]
}
---

# 运维案例库（示例）

## OPS-ORDER-001
- 接口：`POST /api/v1/orders`
- 现象：下单失败，返回 500
- 根因：空订单项未校验
- 处置：应用层参数校验 + 聚合根不变式强化

## OPS-PAYMENT-001
- 接口：`POST /api/v1/payments/confirm`
- 现象：支付确认重复回调导致状态冲突
- 根因：幂等键不完整
- 处置：唯一约束 + 应用层幂等

## OPS-INVENTORY-001
- 接口：`POST /api/v1/inventory/reservations`
- 现象：库存预占超时
- 根因：热点锁竞争
- 处置：分片 + 异步预占
