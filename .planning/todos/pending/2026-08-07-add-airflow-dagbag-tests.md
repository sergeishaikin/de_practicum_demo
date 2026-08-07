---
created: 2026-08-07T18:08:39.341Z
title: Add Airflow DagBag tests
area: testing
files:
  - dags/lakehouse_maintenance.py
  - tests/test_dags.py
---

## Problem

DAG health is only checked manually (`airflow dags trigger`). The review recommends DagBag tests so regressions are caught in milliseconds: DAG imports without error, expected tasks exist, task dependencies are correct, and the schedule is valid.

## Solution

Add `tests/test_dags.py` using Airflow's `DagBag`:
- `dagbag.import_errors == {}` (catches syntax/import breakage).
- Maintenance DAG present; expected task ids exist (`check_bronze_orders_snapshots`, `expire_snapshots_bronze_orders`, etc.).
- Dependency assertions (e.g. `expire_snapshots_bronze_orders >> optimize_...` or whatever the actual wiring is).
- Schedule is a valid cron expression / interval; DAG `schedule_interval` non-null.
- Requires airflow installed in the test env (or a lightweight fixture that imports the DAG module with `AIRFLOW__` env stubs for operators).
