---
created: 2026-08-07T18:08:39.341Z
title: Fix build_silver crash on all-null hashed column BUG-004
area: testing
files:
  - iceberg/medallion/iceberg_medallion.py:118
  - tests/test_medallion.py
---

## Problem

`build_silver` raises `ArrowNotImplementedError` ("Function 'hash_first_last' has no kernel matching input types (null, uint32)") when any hashed column consists entirely of NULL values (e.g. an all-null `event_time` in a bronze scan). PyArrow has no `hash_first` kernel for a null-typed column. In the running service this crashes the medallion cycle and is only swallowed by `main()`'s error handler, so a batch is silently lost. Found during the unit-test phase (2026-08-07); the review rates it BUG-004, Priority: Medium.

## Solution

- Handle null-typed hashed columns before `group_by` — e.g. cast all-null columns to their target type (`timestamp[us]`, `int32`, etc.) so `hash_first` has a kernel, or filter/skip. Do NOT silently drop the batch.
- Add a regression test: `build_silver` on a table with an entirely null `event_time` (and null `kafka_timestamp`) must succeed and preserve the rows.
- Consider aligning with `SILVER_SCHEMA` types so the bronze→silver cast is explicit.
- Document the fix in the todo completion notes.
