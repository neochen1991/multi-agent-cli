---
{
  "type": "domain_aggregate_responsibility",
  "version": "1.0",
  "mappings": [
    {
      "domain": "order",
      "domain_name": "订单域",
      "aggregate": "OrderAggregate",
      "owner_team": "order-domain-team",
      "owner": "alice",
      "api_endpoints": [
        {
          "method": "POST",
          "path": "/api/v1/orders",
          "service": "order-service",
          "interface": "OrderController#createOrder"
        },
        {
          "method": "GET",
          "path": "/api/v1/orders/{orderId}",
          "service": "order-service",
          "interface": "OrderController#getOrder"
        }
      ],
      "code_artifacts": [
        {
          "path": "src/main/java/com/acme/order/interfaces/OrderController.java",
          "symbol": "OrderController#createOrder"
        },
        {
          "path": "src/main/java/com/acme/order/application/OrderAppService.java",
          "symbol": "OrderAppService#createOrder"
        },
        {
          "path": "src/main/java/com/acme/order/domain/aggregate/OrderAggregate.java",
          "symbol": "OrderAggregate#placeOrder"
        },
        {
          "path": "src/main/java/com/acme/order/infrastructure/OrderRepositoryImpl.java",
          "symbol": "OrderRepositoryImpl#save"
        }
      ],
      "db_tables": ["t_order", "t_order_item", "t_order_snapshot"],
      "design_refs": [
        {
          "doc": "domain-aggregate-design.md",
          "section": "订单域 / OrderAggregate"
        }
      ],
      "keywords": ["下单", "order create", "create order", "订单创建失败"]
    },
    {
      "domain": "payment",
      "domain_name": "支付域",
      "aggregate": "PaymentAggregate",
      "owner_team": "payment-domain-team",
      "owner": "bob",
      "api_endpoints": [
        {
          "method": "POST",
          "path": "/api/v1/orders/{orderId}/pay",
          "service": "payment-service",
          "interface": "OrderPaymentController#payOrder"
        },
        {
          "method": "POST",
          "path": "/api/v1/payments/confirm",
          "service": "payment-service",
          "interface": "PaymentController#confirmPayment"
        }
      ],
      "code_artifacts": [
        {
          "path": "src/main/java/com/acme/payment/interfaces/PaymentController.java",
          "symbol": "PaymentController#confirmPayment"
        },
        {
          "path": "src/main/java/com/acme/payment/application/PaymentAppService.java",
          "symbol": "PaymentAppService#confirm"
        },
        {
          "path": "src/main/java/com/acme/payment/domain/aggregate/PaymentAggregate.java",
          "symbol": "PaymentAggregate#confirm"
        },
        {
          "path": "src/main/java/com/acme/payment/infrastructure/PaymentRepositoryImpl.java",
          "symbol": "PaymentRepositoryImpl#updateStatus"
        }
      ],
      "db_tables": ["t_payment", "t_payment_attempt", "t_payment_reconciliation"],
      "design_refs": [
        {
          "doc": "domain-aggregate-design.md",
          "section": "支付域 / PaymentAggregate"
        }
      ],
      "keywords": ["支付", "payment", "confirm payment", "支付确认失败"]
    },
    {
      "domain": "inventory",
      "domain_name": "库存域",
      "aggregate": "InventoryAggregate",
      "owner_team": "inventory-domain-team",
      "owner": "carol",
      "api_endpoints": [
        {
          "method": "POST",
          "path": "/api/v1/inventory/reservations",
          "service": "inventory-service",
          "interface": "InventoryReservationController#createReservation"
        },
        {
          "method": "POST",
          "path": "/api/v1/inventory/reservations/{reservationId}/release",
          "service": "inventory-service",
          "interface": "InventoryReservationController#releaseReservation"
        }
      ],
      "code_artifacts": [
        {
          "path": "src/main/java/com/acme/inventory/interfaces/InventoryReservationController.java",
          "symbol": "InventoryReservationController#createReservation"
        },
        {
          "path": "src/main/java/com/acme/inventory/application/InventoryReservationAppService.java",
          "symbol": "InventoryReservationAppService#reserve"
        },
        {
          "path": "src/main/java/com/acme/inventory/domain/aggregate/InventoryAggregate.java",
          "symbol": "InventoryAggregate#reserve"
        },
        {
          "path": "src/main/java/com/acme/inventory/infrastructure/InventoryRepositoryImpl.java",
          "symbol": "InventoryRepositoryImpl#decreaseAvailable"
        }
      ],
      "db_tables": ["t_inventory", "t_inventory_reservation", "t_inventory_txn_log"],
      "design_refs": [
        {
          "doc": "domain-aggregate-design.md",
          "section": "库存域 / InventoryAggregate"
        }
      ],
      "keywords": ["库存", "inventory", "reserve", "库存预占失败"]
    }
  ]
}
---

# 领域-聚合根责任田清单（示例）

| 领域 | 聚合根 | 责任团队 | 负责人 | 核心接口 | 核心代码 | 数据库表 |
|---|---|---|---|---|---|---|
| 订单域 | OrderAggregate | order-domain-team | alice | POST /api/v1/orders | OrderController / OrderAppService / OrderAggregate | t_order / t_order_item / t_order_snapshot |
| 支付域 | PaymentAggregate | payment-domain-team | bob | POST /api/v1/payments/confirm | PaymentController / PaymentAppService / PaymentAggregate | t_payment / t_payment_attempt / t_payment_reconciliation |
| 库存域 | InventoryAggregate | inventory-domain-team | carol | POST /api/v1/inventory/reservations | InventoryReservationController / InventoryReservationAppService / InventoryAggregate | t_inventory / t_inventory_reservation / t_inventory_txn_log |

> 用途：当日志里出现接口 URL（如 `/api/v1/orders`）时，系统可直接映射到对应领域与聚合根，并给出代码、表与设计文档定位信息。
