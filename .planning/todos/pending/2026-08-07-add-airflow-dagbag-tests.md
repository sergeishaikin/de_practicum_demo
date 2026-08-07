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
