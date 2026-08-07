---
created: 2026-08-07T18:08:39.341Z
title: Add writer crash-recovery integration test
area: testing
files:
  - iceberg/writer/iceberg_writer.py:51
  - iceberg/writer/iceberg_writer.py:260
  - iceberg/writer/iceberg_writer.py:290
  - tests/test_writer.py
---

## Problem

The writer's crash-recovery path (`SIMULATE_CRASH_BEFORE_COMMIT` / `SIMULATE_CRASH_AFTER_COMMIT`, `os._exit`) is not exercised automatically — the review flagged this as the biggest remaining unit-level gap. The `recover_pending` logic is unit-tested but the full "crash → restart → no duplicates" invariant is only covered by fakes.

## Solution

Add `tests/integration/test_crash_recovery.py`:
- start the writer loop (or a fixture that drives `load_state`/`recover_pending`/`committed_load_ids`),
- inject a crash before commit, restart, assert the load is re-appended exactly once (same `load_id`, same row count, no duplicates);
- inject a crash after commit, restart, assert the load is marked done and NOT re-appended.
- Use real MinIO + REST catalog if possible; otherwise a staged FakeCatalog that persists across restarts.
