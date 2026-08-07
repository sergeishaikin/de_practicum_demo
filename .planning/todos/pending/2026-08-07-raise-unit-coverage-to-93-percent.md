---
created: 2026-08-07T18:08:39.341Z
title: Raise unit coverage to 93 percent
area: testing
files:
  - tests/test_medallion.py
  - tests/test_writer.py
  - tests/test_ops.py
---

## Problem

Unit coverage is 90% overall (ops 96%, medallion 90%, writer 88%). The review suggests 90% → 93% by adding cases for the quality-failure branches and the maintenance/retry edge paths that are currently untested.

## Solution

Add targeted tests:
- Quality failures: invalid `status`, negative amount, future timestamp, duplicate `kafka_offset`.
- Retry exhaustion: `MAX_APPEND_ATTEMPTS` reached → commit re-raised → error path cleans pending (partially covered; add explicit exhaustion-on-last-attempt assert).
- Maintenance helpers: SQL generation for `expire_snapshots`, `optimize`, `remove_orphan_files` and orphan cleanup logic (extract to a pure helper if needed).
- Optional: `Metrics.close()` exception-swallow branch (`ops.py:118-119`).
Keep the suite fast and dependency-free.
