---
phase: 01-b2-controlled-rollout
plan: 06
status: complete
disposition: PASS
ready_for_01_07: true
completed: 2026-08-10
---

# 01-06 Summary — Representative O1 Telemetry Window

The bounded remediation added production B2 physical-cost instrumentation and
focused read/write/no-op coverage. The mounted medallion was restarted without
changing the accepted `b2/persisted_silver/1` tuple.

One higher-version event for existing key `nb-order-001` traversed Kafka,
Spark Landing, the Bronze writer, and B2 Silver. The temporary streaming and
writer services were stopped again after one row and one file; outbox and
in-flight progress returned to zero.

The unchanged 01-06 validity gate passed on ten consecutive successful rows:

- one non-empty B2 row with one key and one input file;
- 1 file / 4,422 bytes planned;
- 0 files / 0 bytes removed;
- 1 file / 4,299 bytes added;
- one Silver snapshot and 5,805 ms Silver duration;
- five shadow comparisons, zero mismatches, zero FF-14 conflicts, and final
  in-flight work of zero.

Focused tests: 40 passed across B2 medallion, legacy medallion, and metrics
tests. Ruff lint passed for the changed Python files.

Disposition: `PASS`, `ready_for_01_07=true`. Plan 01-07 was not executed, and
neither D-3a nor O2 was opened.
