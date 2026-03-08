# Order Timeout Mock Scenario

## Scenario
- service entry: order-service
- root symptom: POST /api/v1/orders returns 500 and latency spikes above 12s
- trace_id: trc-20260308-9001
- business chain: order-service -> inventory-service -> payment-service
- likely root path: hot inventory row lock waits amplify order transaction time, then Hikari pool exhausts

## Local assets
- monorepo: ./order-platform-monorepo
- combined log: ./logs/platform-error.log
- per-service logs: ./logs/order-service-error.log ./logs/inventory-service.log ./logs/payment-service.log
- responsibility csv: ./docs/order-domain-responsibility.csv
- database snapshot: ./docs/order_center_snapshot.sqlite
- database reference doc: ./docs/postgres_schema_reference.md
- metrics reference doc: ./metrics/order_metrics_reference.md
- metrics window csv: ./metrics/order_metrics_window.csv

## System config written
- tooling config: /tmp/sre_debate_store/tooling_config.json
- responsibility assets: /tmp/sre_debate_store/assets/responsibility_assets.json
