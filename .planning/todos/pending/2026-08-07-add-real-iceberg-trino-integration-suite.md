---
created: 2026-08-07T18:08:39.341Z
title: Add real Iceberg Trino integration suite
area: testing
priority: 3
files:
  - tests/integration/
  - docker-compose.yml
---

## Problem

The unit suite mocks catalog, S3, and Postgres entirely. No automated tests run against the real MinIO + REST catalog + Iceberg tables or Trino. The review scores integration automation 6.5/10. Slower (1–3 min) but validates lakehouse invariants fakes cannot.

## Solution

Split into several SHORT tests, not one big one (each behind `@pytest.mark.integration`):

1. `test_catalog_connectivity.py` — REST catalog + MinIO reachable, namespace/table ops.
2. `test_iceberg_append_snapshots.py` — append via real catalog; snapshots created; `load-id` in snapshot summary.
3. `test_time_travel.py` — read a previous snapshot by timestamp/version.
4. `test_silver_dedup.py` — dedup by `order_id`, latest `kafka_offset` wins, verified against real silver table.
5. `test_gold_reconciliation.py` — deterministic aggregation values (e.g. UK revenue 1250, US revenue 900, total 2150), not `count > 0`.
6. `test_trino_select.py` — `SELECT` across bronze/silver/gold.
7. `test_trino_maintenance.py` — maintenance SQL: `expire_snapshots`, `optimize`, `remove_orphan_files`.

Use an isolated namespace per run so tests never touch demo tables:

```text
test_<run_id>.bronze_orders
test_<run_id>.silver_orders_clean
test_<run_id>.gold_orders_daily_metrics
```

and drop it in a fixture teardown. This layer depends on the pytest markers + `stack.ps1` infra todo being done first.
