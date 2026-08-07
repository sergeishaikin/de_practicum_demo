---
created: 2026-08-07T18:08:39.341Z
title: Strengthen unit coverage of critical failure paths
area: testing
priority: lowest (deferred; 90% threshold is acceptable)
files:
  - tests/test_medallion.py
  - tests/test_writer.py
  - tests/test_ops.py
---

## Problem

Unit coverage is 90% overall (ops 96%, medallion 90%, writer 88%). Raising the number from 90% → 93% is NOT valuable by itself — only if the extra points cover real failure paths. Defer this until the integration/E2E/CI todos are done; real failure modes matter more than the percentage.

## Solution

Only if time permits and the added coverage targets real branches, not filler:

- Quality failures: invalid `status`, negative amount, future timestamp, duplicate `kafka_offset`.
- Retry exhaustion: `MAX_APPEND_ATTEMPTS` reached → commit re-raised → error path cleans pending (partially covered; add explicit exhaustion-on-last-attempt assert).
- Maintenance helpers: SQL generation for `expire_snapshots`, `optimize`, `remove_orphan_files` and orphan cleanup logic (extract to a pure helper if needed).
- Optional: `Metrics.close()` exception-swallow branch (`ops.py:118-119`).

Keep the suite fast and dependency-free.
