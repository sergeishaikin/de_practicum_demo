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

## Done (2026-08-07)

- Added markers `iceberg` and `trino` to `pytest.ini`; every test carries `integration` + its narrower marker.
- Added `tests/integration/test_iceberg_trino.py` — 7 short, deterministic tests against `test_<run_id>` namespaces on the live stack (MinIO `localhost:19000`, REST catalog `localhost:18181`, Trino `localhost:18082` via `docker exec de-demo-trino trino --output-format CSV_HEADER`):
  1. `test_catalog_and_table_creation_visible_in_trino` — create via REST catalog, visible via `SHOW TABLES` in Trino.
  2. `test_append_increases_snapshot_and_records_load_id` — snapshot count 0→1→2; `load-id` read back from snapshot summary.
  3. `test_silver_dedup_latest_offset_wins` — real `build_silver`: `a@offset5(50)` wins over `a@offset1(10)`.
  4. `test_gold_aggregation_exact_values` — UK 4 orders/1250.0/2 customers, US 4/900.0/2, total 2150.0, verified in PyIceberg AND Trino.
  5. `test_trino_select_across_layers` — bronze 3, silver 3, `sum(total_amount)=60.0` through Trino.
  6. `test_time_travel_snapshot_history` — append batch2, current count 2, `FOR VERSION AS OF <first_snapshot>` count 1.
  7. `test_maintenance_procedures` — `optimize`/`expire_snapshots`/`remove_orphan_files` complete on the real table; row count preserved; snapshot count behaves (optimize ≥ before, expire ≤ after-optimize, still ≥ 1).
- Defensive cleanup fixture: `try`-teardown drops tables + namespace via catalog AND `DROP SCHEMA IF EXISTS ... CASCADE` via Trino (backstop for failed tests). Verified: only `bronze/gold/silver` namespaces remain after the run.
- Results: **9 passed** integration (2 crash-recovery + 7 Iceberg/Trino) in ~68s; fast suite still **39 passed, 9 deselected**.
- Learning: Trino `optimize(file_size_threshold => ...)` requires lowercase size units (`5MB`), not `1KB`.

