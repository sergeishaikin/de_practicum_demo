---
created: 2026-08-07T18:08:39.341Z
title: Nightly E2E lakehouse system test
area: testing
priority: 6
files:
  - tests/e2e/
  - spark/
  - docker-compose.yml
---

## Problem

The full pipeline Kafka → Spark → landing → Iceberg bronze → silver → gold → Trino → metrics is only validated manually. This is the most valuable automated system test the project can have.

## Solution

Add `tests/e2e/` (`@pytest.mark.e2e`, nightly-only) driven by a **deterministic fixture**, NOT an endless producer. A fixture of exactly 100 Kafka events with a pre-known result:

```text
100 Kafka messages
96 unique order IDs
3 updates to existing IDs
1 invalid status
```

Expected invariants (assert exact values, not `count > 0`):

```text
Silver valid rows = 95
UK revenue = exact known value
US revenue = exact known value
Gold total = exact known value
```

Pipeline: deterministic fixture → Kafka → Spark 4.2 → landing → writer → Iceberg Bronze → Silver → Gold → Trino assertions → metrics assertions (`marts.lakehouse_metrics` rows). Assert business invariants end-to-end. Depends on markers/`stack.ps1` infra and a healthy Compose stack.
