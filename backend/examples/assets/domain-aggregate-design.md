---
{
  "type": "domain_aggregate_design",
  "version": "1.0",
  "domains": [
    {
      "domain": "order",
      "name": "订单域",
      "description": "负责订单创建、状态流转与订单快照维护。",
      "aggregates": [
        {
          "name": "OrderAggregate",
          "description": "订单核心聚合，负责订单生命周期管理。",
          "invariants": [
            "订单必须至少包含一个订单项",
            "已支付订单禁止重复支付",
            "订单状态流转必须遵循 Created -> Confirmed -> Paid -> Fulfilled"
          ],
          "entities": ["Order", "OrderItem"],
          "value_objects": ["OrderId", "Money", "OrderStatus"],
          "domain_services": ["OrderPricingDomainService", "OrderValidationService"],
          "events": ["OrderCreated", "OrderPaid", "OrderCancelled"],
          "interfaces": [
            "POST /api/v1/orders",
            "GET /api/v1/orders/{orderId}",
            "POST /api/v1/orders/{orderId}/cancel"
          ]
        }
      ]
    },
    {
      "domain": "payment",
      "name": "支付域",
      "description": "负责支付确认、支付状态回写与重试补偿。",
      "aggregates": [
        {
          "name": "PaymentAggregate",
          "description": "支付核心聚合，保障支付事务一致性。",
          "invariants": [
            "支付请求必须绑定有效订单",
            "同一支付流水号只能确认一次",
            "支付成功后必须回写订单状态"
          ],
          "entities": ["Payment", "PaymentAttempt"],
          "value_objects": ["PaymentId", "PaymentChannel", "PaymentStatus"],
          "domain_services": ["PaymentRetryService", "PaymentReconciliationService"],
          "events": ["PaymentConfirmed", "PaymentFailed"],
          "interfaces": [
            "POST /api/v1/orders/{orderId}/pay",
            "POST /api/v1/payments/confirm"
          ]
        }
      ]
    },
    {
      "domain": "inventory",
      "name": "库存域",
      "description": "负责库存预占、释放与扣减。",
      "aggregates": [
        {
          "name": "InventoryAggregate",
          "description": "库存核心聚合，确保库存不被超卖。",
          "invariants": [
            "可售库存不得为负数",
            "预占库存必须绑定订单号",
            "订单取消必须释放预占库存"
          ],
          "entities": ["Inventory", "Reservation"],
          "value_objects": ["SkuId", "WarehouseId", "Quantity"],
          "domain_services": ["InventoryReservationService", "InventoryReleaseService"],
          "events": ["InventoryReserved", "InventoryReleased"],
          "interfaces": [
            "POST /api/v1/inventory/reservations",
            "POST /api/v1/inventory/reservations/{reservationId}/release"
          ]
        }
      ]
    }
  ]
}
---

# 领域-聚合根详细设计示例

## 订单域 / OrderAggregate
- 核心职责：接收下单请求，进行订单校验、价格计算、持久化与事件发布。
- 关键流程：
  1. `OrderController#createOrder` 接收请求。
  2. `OrderAppService#createOrder` 执行应用编排。
  3. `OrderAggregate#placeOrder` 校验不变式并构建聚合。
  4. `OrderRepository#save` 落库并发布 `OrderCreated` 事件。
- 失败场景重点：空订单项、价格计算失败、库存预占失败。

## 支付域 / PaymentAggregate
- 核心职责：确认支付、记录支付流水、回写订单状态。
- 关键流程：
  1. `PaymentController#confirmPayment` 接收支付回调。
  2. `PaymentAppService#confirm` 做幂等校验。
  3. `PaymentAggregate#confirm` 更新支付状态。
  4. 发布 `PaymentConfirmed`，触发订单状态变更。
- 失败场景重点：重复回调、上游超时、回写订单失败。

## 库存域 / InventoryAggregate
- 核心职责：库存预占、库存释放、库存扣减。
- 关键流程：
  1. `InventoryReservationController#createReservation` 接收预占请求。
  2. `InventoryReservationAppService#reserve` 执行业务校验。
  3. `InventoryAggregate#reserve` 更新库存与预占记录。
  4. 发布 `InventoryReserved` 事件。
- 失败场景重点：并发预占、库存不足、释放补偿失败。
