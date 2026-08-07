---
created: 2026-08-07T18:08:39.341Z
title: Add Airflow DagBag tests
area: testing
priority: 4
files:
  - dags/lakehouse_maintenance.py
  - tests/test_dags.py
---

## Problem

DAG health is only checked manually (`airflow dags trigger`). DagBag tests catch regressions in milliseconds and cost almost nothing.

## Solution

Add `tests/test_dags.py` (marked `airflow`):

- `dagbag.import_errors == {}` — catches syntax/import breakage.
- Maintenance DAG exists; expected task ids present (`check_bronze_orders_snapshots`, `expire_snapshots_bronze_orders`, `optimize_...`, `remove_orphan_files_...`, etc.).
- Dependencies correct — assert the actual `>>` / `set_downstream` wiring.
- Schedule valid — cron expression / interval parses; `schedule_interval` non-null.
- Retries / timeout where relevant — `retries >= 1` on maintenance tasks.

Do NOT drag full Airflow into the ordinary unit env if it bloats CI — run DAG tests in a separate `airflow-tests` job/container (or a lightweight fixture importing the DAG module with `AIRFLOW__` operator stubs).

## Done (2026-08-07)

Implemented via the existing `de-demo-airflow` container (Airflow 2.9.3): `tests/test_dags.py` pipes `scripts/dump_dag_structure.py` into `docker exec -i de-demo-airflow python -`, gets the DagBag structure as JSON, and asserts on the host. No host Airflow install. 8 tests, all passing.

- Real graph asserted (not imagined): the DAG's task ids are `capture_before`, `optimize_tables`, `expire_snapshots_tables`, `remove_orphan_files_tables`, `write_audit` (NOT the ids guessed in this todo). Dependencies from DagBag: `capture_before → optimize_tables → expire_snapshots_tables → remove_orphan_files_tables`, and `write_audit` depends on **both** `capture_before` and `remove_orphan_files_tables` (merge at the end).
- `import_errors == {}`; `schedule == "0 * * * *"`, `catchup=False`, `max_active_runs=1`.
- `default_retries == 0`, `execution_timeout == 15m` (real DAG uses retries 0, not `>= 1` as guessed in this todo).
- `MAINTENANCE_TABLES` is **hardcoded** (bronze.orders, silver.orders_clean, gold.orders_daily_metrics) — not env-driven — so tests assert the literal list + sane values (RETAIN_LAST=5, RETENTION=1h, FILE_SIZE_THRESHOLD=10MB). The "malformed env tables → fail clearly" idea from the plan does not apply to the current implementation.
- `pytest.ini` addopts now excludes `airflow` too: fast suite stays Docker-free (39 passed / 17 deselected); DAG tests run via `pytest tests/test_dags.py -m airflow`.
