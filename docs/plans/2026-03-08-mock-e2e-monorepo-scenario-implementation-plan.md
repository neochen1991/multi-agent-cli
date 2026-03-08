# Mock E2E Monorepo Scenario Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构造一套单仓多服务的本地真实事故现场数据，供当前多 Agent 系统执行端到端排障分析。

**Architecture:** 复用系统现有本地工具接入路径，不改运行时逻辑。通过一个 monorepo、连续日志、责任田 CSV、SQLite 数据库快照和指标参考文档共同组成完整事故现场，并把这些文件写入系统当前会读取的配置位置。

**Tech Stack:** Python 3, SQLite, Git, CSV, Markdown, Java source stubs

---

### Task 1: Rebuild Mock Monorepo Structure

**Files:**
- Modify: `mock_data/order_timeout_scenario/order-service/**`
- Create: `mock_data/order_timeout_scenario/order-platform-monorepo/**`

**Step 1: Remove the thin single-service mock from the active path**

Run: `find mock_data/order_timeout_scenario -maxdepth 3 -type f | sort`
Expected: Confirm current thin layout before replacement.

**Step 2: Create monorepo directories**

Create:
- `mock_data/order_timeout_scenario/order-platform-monorepo/services/order-service`
- `mock_data/order_timeout_scenario/order-platform-monorepo/services/inventory-service`
- `mock_data/order_timeout_scenario/order-platform-monorepo/services/payment-service`
- `mock_data/order_timeout_scenario/order-platform-monorepo/docs/change-notes`
- `mock_data/order_timeout_scenario/order-platform-monorepo/sql`

**Step 3: Add minimal but realistic Java source files**

Add controllers, application services, repositories, client calls, and config files that encode the cross-service path.

**Step 4: Initialize git history**

Run: `git init && git add . && git commit -m "feat: add mock order platform monorepo"`
Expected: Local branch `main` with at least one commit.

### Task 2: Expand Log Timeline

**Files:**
- Modify: `mock_data/order_timeout_scenario/logs/order-service-error.log`
- Create: `mock_data/order_timeout_scenario/logs/inventory-service.log`
- Create: `mock_data/order_timeout_scenario/logs/payment-service.log`
- Create: `mock_data/order_timeout_scenario/logs/traffic-timeline.md`

**Step 1: Write a multi-phase timeline**

Include normal, degradation, peak failure, and pre-recovery windows.

**Step 2: Add consistent identifiers**

All logs must reuse aligned `traceId`, `orderNo`, `skuCode`, service names, API names, and table names.

**Step 3: Embed metric signals in log text**

Ensure the existing `MetricsAgent` implementation can extract CPU, threads, Hikari pending, DB connections, and latency directly from text.

### Task 3: Expand Responsibility Mapping

**Files:**
- Modify: `mock_data/order_timeout_scenario/docs/order-domain-responsibility.csv`
- Modify: `/tmp/sre_debate_store/assets/responsibility_assets.json`

**Step 1: Add three responsibility rows**

Add rows for order submission, inventory deduction, and payment reservation.

**Step 2: Keep fields aligned**

Match every row’s APIs, code classes, DB tables, dependencies, and monitor items to the monorepo and logs.

**Step 3: Rewrite the local asset JSON**

Persist the same content into `/tmp/sre_debate_store/assets/responsibility_assets.json` so the running system sees the expanded mapping.

### Task 4: Expand Database Snapshot

**Files:**
- Modify: `mock_data/order_timeout_scenario/docs/order_center_snapshot.sqlite`
- Modify: `mock_data/order_timeout_scenario/docs/postgres_schema_reference.md`

**Step 1: Add richer schema**

Create `t_payment_record` and `lock_waits` alongside existing business and diagnostic tables.

**Step 2: Add realistic rows**

Populate slow SQL, top SQL, session status, lock waits, and representative inventory/payment records.

**Step 3: Verify query compatibility**

Run sqlite checks to confirm the tables match what `DatabaseAgent` currently queries.

### Task 5: Expand Metrics Materials

**Files:**
- Modify: `mock_data/order_timeout_scenario/metrics/order_metrics_reference.md`
- Create: `mock_data/order_timeout_scenario/metrics/order_metrics_window.csv`

**Step 1: Add minute-level windows**

Document the abnormal metric evolution across the incident window.

**Step 2: Keep names aligned**

Use the exact monitor item names referenced in responsibility assets and logs.

### Task 6: Rewrite Tooling Config to Point at the New Monorepo Scenario

**Files:**
- Modify: `/tmp/sre_debate_store/tooling_config.json`
- Modify: `mock_data/order_timeout_scenario/README.md`

**Step 1: Point code repo to the monorepo path**

Update `code_repo.local_repo_path`.

**Step 2: Keep other tool paths aligned**

Update log file, domain CSV, and SQLite snapshot paths.

**Step 3: Write usage notes**

Document all generated paths in the README.

### Task 7: Validate End-to-End Data Integrity

**Files:**
- Verify only

**Step 1: Verify git repo exists and has commit history**

Run: `git -C mock_data/order_timeout_scenario/order-platform-monorepo log --oneline -3`
Expected: At least one commit exists.

**Step 2: Verify SQLite tables**

Run sqlite inspection to confirm business and diagnostic tables are readable.

**Step 3: Verify system config files**

Read `/tmp/sre_debate_store/tooling_config.json` and `/tmp/sre_debate_store/assets/responsibility_assets.json`.
Expected: Paths and fields match the new monorepo scenario.
