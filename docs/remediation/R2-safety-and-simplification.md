# R2 — Safety and simplification closure

Status: **implemented and verified**.

R2 is deliberately limited to safety around the existing M1–M5 architecture. It
does not change D-3a physical layout, add observability infrastructure, add
multi-writer support, or remove the recovery state machine.

## R2.1 Atomic writer state

The writer state file is now written to a sibling temporary file, flushed,
`fsync`'d, and atomically replaced with `os.replace`. A failed replacement
leaves the previous complete JSON document intact and temporary siblings are
cleaned up. This protects the existing done/pending and snapshot-summary
recovery semantics from a process interruption during serialization.

## R2.2 Pinned shadow boundary

For B2 shadow runs, Bronze is materialized once before B2 executes as a
`BronzeBoundary`. The legacy candidate is built from that pinned boundary and
the persisted B2 result is compared after B2 commits. A later live Bronze scan
cannot silently move one side of the comparison to a different ingestion
state. Duplicate-key selection and diagnostics are canonically ordered so
physical Arrow/file row order does not change the result.

## R2.3 Runtime rollout safety

The medallion validates its startup configuration against the allowed rollout
matrix. The legacy default, B2 shadow rollout, B2 rollback to legacy Gold, and
shadow-protected persisted-Silver cutover are allowed. `b2 +
persisted_silver + shadow=0` is rejected before the service loop starts.

## R2.4 PostgreSQL semantics

`marts.streaming_orders` remains an independent low-latency serving/cache
surface. Its conflict update is now monotonic on `business_version`; a null,
lower, or equal version cannot overwrite a newer current row. The PyIceberg
medallion remains authoritative for current-state semantics and FF-14
conflict handling.

## Verification record

The following evidence was executed against the current working tree:

```text
ruff check .
All checks passed

python -m pytest -q --basetemp .pytest-r2-focused \
  tests/test_writer.py tests/test_m4_gold.py tests/test_m5_fitness_functions.py
48 passed

python -m pytest -q --basetemp .pytest-r2-fast
102 passed, 30 deselected

python -m pytest -q -m integration --basetemp .pytest-r2-integration \
  tests/integration/test_crash_recovery.py \
  tests/integration/test_m3_b2_recovery.py \
  tests/integration/test_m4_gold_cutover.py -s
4 passed

python -m pytest -q -m e2e --basetemp .pytest-r2-e2e \
  tests/e2e/test_lakehouse_e2e.py -s
1 passed
```

The startup probe with `SILVER_MODE=b2`, `GOLD_SOURCE=persisted_silver`, and
`SHADOW_COMPARE=0` failed fast with the expected unsafe-configuration
`ValueError`. `git diff --check` also passed.

Residual risks: PostgreSQL remains a separately implemented serving projection,
and writer recovery still depends on retained Iceberg snapshot summaries as
recorded by F-301.
