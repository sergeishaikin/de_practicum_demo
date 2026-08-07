---
created: 2026-08-07T18:08:39.341Z
title: Add writer crash-recovery integration test
area: testing
priority: 2
files:
  - iceberg/writer/iceberg_writer.py:51
  - iceberg/writer/iceberg_writer.py:260
  - iceberg/writer/iceberg_writer.py:290
  - tests/integration/test_crash_recovery.py
---

## Problem

The writer's crash-recovery path (`SIMULATE_CRASH_BEFORE_COMMIT` / `SIMULATE_CRASH_AFTER_COMMIT`, `os._exit`) is not exercised automatically — the review flagged this as the biggest remaining gap. `recover_pending` is unit-tested but the full "crash → restart → no duplicates" invariant is only proven with fakes. Crash recovery is one of the strongest parts of the architecture, so it must be proven automatically.

## Solution

Add `tests/integration/test_crash_recovery.py` covering both crash points, using real MinIO + REST catalog where possible:

- **Crash before commit** → restart → the load is re-appended exactly once: same `load_id`, same row count, no duplicate rows.
- **Crash after commit** → restart → the load is marked done and NOT re-appended.
- Assert the state transitions too, not just row counts:
  - `load-id` present in the snapshot summary after commit;
  - `pending → done` transition in the state file (`STATE_FILE`), and a cleared `pending` for that load after recovery.
- Drive via the writer loop fixture (real `os._exit` injection or a subprocess restart).
