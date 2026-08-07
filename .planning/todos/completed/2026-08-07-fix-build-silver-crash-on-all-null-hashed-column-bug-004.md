---
created: 2026-08-07T18:08:39.341Z
title: Fix build_silver crash on all-null hashed column BUG-004
area: testing
priority: 1
files:
  - iceberg/medallion/iceberg_medallion.py:118
  - tests/test_medallion.py
---

## Problem

`build_silver` raises `ArrowNotImplementedError` ("Function 'hash_first_last' has no kernel matching input types (null, uint32)") when any hashed column consists entirely of NULL values (e.g. an all-null `event_time` in a bronze scan). PyArrow has no `hash_first` kernel for a null-typed column. In the running service this crashes the medallion cycle and is only swallowed by `main()`'s error handler, so a batch is silently lost. Found during the unit-test phase (2026-08-07); the review rates it BUG-004, Priority: Medium.

## Solution

Do this FIRST — it is a real defect that can silently stop the Silver cycle today.

- Handle null-typed hashed columns before `group_by` — e.g. cast all-null columns to their target type (`timestamp[us]`, `int32`, etc.) so `hash_first` has a kernel, or filter/skip. Do NOT silently drop the batch.
- Add a regression test: `build_silver` on a table with an entirely null `event_time` (and null `kafka_timestamp`) must succeed and preserve the rows.
- Consider aligning with `SILVER_SCHEMA` types so the bronze→silver cast is explicit.
- Document the fix in the todo completion notes.

## Done (2026-08-07)

- Added `_normalize_null_typed_columns()` in `iceberg/medallion/iceberg_medallion.py`; `build_silver` casts only null-typed columns to their expected silver type (`_SILVER_TYPES` map: `event_time`/`kafka_timestamp` → `timestamp[us]`, `kafka_partition` → `int32`, `kafka_offset` → `int64`, strings stay `string`). Non-null columns are left untouched — no behavior/type change for normal data. Did NOT use `SILVER_SCHEMA.as_arrow()` because pyiceberg maps strings to `large_string`.
- Regression tests added: `test_handles_all_null_event_time` and `test_handles_all_null_sort_and_hash_columns` (all-null `kafka_offset` + `event_date`).
- Suite: **39 passed** (37 prior + 2 new), coverage steady at **90%**.
- Live verification: restarted `de-demo-iceberg-medallion` (code is bind-mounted), one real cycle completed (`silver.orders_clean` overwritten, gold 72 daily metrics); BUG-004 path exec'd inside the container with an all-null `event_time` batch → no crash, `event_time` typed `timestamp[us]`; `quality_violations=0` and fresh `medallion|success` rows in `marts.lakehouse_metrics`. README/TESTING unchanged (no external behavior change).

