# M4 — Persisted-Silver Gold, shadow validation, and controlled cutover

Status: **implementation complete**.

M4 changes the Gold input boundary while preserving both existing execution paths. Silver remains
selectable with `SILVER_MODE=legacy` or `SILVER_MODE=b2`; Gold is now selectable with
`GOLD_SOURCE=legacy` or `GOLD_SOURCE=persisted_silver`. M4 does not implement M5 fitness-function
gates or D-3a physical layout tuning.

## Previous behaviour and the M4 boundary

The legacy medallion cycle scanned all Bronze rows, rebuilt the current Silver projection, wrote a
full Silver overwrite, and immediately built Gold from that in-memory Silver result. This was
correct for the legacy path, but it meant that Gold had no explicit dependency on the persisted
Silver table.

M4 makes the dependency explicit:

```text
Bronze outbox
      │
      ▼
M3 B2 Silver projection ──► persisted Iceberg Silver
                                  │
                                  ▼
                         Gold source selection
                         ├─ legacy projection
                         └─ persisted Silver
                                  │
                                  ▼
                         persisted Iceberg Gold
```

With `SILVER_MODE=b2` and `GOLD_SOURCE=persisted_silver`, Gold reads the committed Silver table
through an Iceberg scan. It does not rebuild Silver from Bronze. The legacy projection is built
only when it is selected as the Gold source or when shadow comparison requires a comparison
candidate.

## Configuration contract

```text
SILVER_MODE=legacy|b2
GOLD_SOURCE=legacy|persisted_silver
SHADOW_COMPARE=0|1
```

The defaults preserve the pre-M4 behaviour:

```text
SILVER_MODE=legacy
GOLD_SOURCE=legacy
SHADOW_COMPARE=0
```

Recommended rollout settings are:

1. `SILVER_MODE=b2`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=1` — validate B2 against the legacy
   logical projection while keeping the legacy Gold input.
2. `SILVER_MODE=b2`, `GOLD_SOURCE=persisted_silver`, `SHADOW_COMPARE=1` — validate and then use
   persisted Silver as the Gold input.

Rollback changes only `GOLD_SOURCE` back to `legacy`. It does not reset Silver, alter B2 progress,
or recreate completed Bronze outbox work. The legacy Gold source remains available throughout the
rollout.

## Deterministic shadow comparison

When `SHADOW_COMPARE=1`, the medallion compares the legacy projection and persisted B2 Silver before
writing Gold. Comparison is a logical current-state comparison keyed by `order_id`; input row
order and physical file order do not matter.

The compared business columns are:

```text
business_version, customer, amount, country,
status, event_time, event_date
```

The following transport-only columns are explicitly excluded:

```text
kafka_timestamp, kafka_partition, kafka_offset
```

Values are normalized null-safely, including dates, timestamps, and NaN. Diagnostics are sorted and
identify the order id and mismatch type. The supported mismatch types are:

```text
duplicate_business_key
missing_in_legacy
missing_in_persisted_b2
business_version_mismatch
payload_mismatch
```

Shadow comparison is fail-closed. A mismatch is emitted to stderr, recorded as
`status=shadow_failed`, and raises before Gold overwrite. Therefore a mismatch cannot silently
produce a Gold result from an untrusted source.

## Commit and recovery ownership

M3 still owns Bronze-to-Silver work state:

```text
Bronze writer load-id / snapshot evidence
        ↓
Bronze outbox
        ↓
M3 Silver progress: available → in-flight → completed
        ↓
persisted Silver commit
```

M4 does not introduce a second durable Gold progress protocol. Gold is overwritten only after the
selected Gold input has been read and, when enabled, shadow validation has succeeded. If Gold
writing fails, the M3 completed marker and outbox semantics are unchanged; the next medallion cycle
can retry Gold without replaying or deleting committed Bronze work. B2 crash-before-commit and
crash-after-commit reconciliation remain M3 responsibilities and are covered by their existing
tests.

## Verification evidence

Static and focused tests:

```text
ruff check .
All checks passed!

python -m pytest -q --basetemp .pytest-m4-focused tests/test_m4_gold.py tests/test_b2_medallion.py tests/test_medallion.py tests/test_writer.py tests/test_b2_spike.py tests/test_order_contract.py
66 passed
```

M3 and writer recovery regression:

```text
python -m pytest -q -m integration --basetemp .pytest-m3-live tests/integration/test_m3_b2_recovery.py -s
1 passed

python -m pytest -q -m integration --basetemp .pytest-crash-live tests/integration/test_crash_recovery.py -s
2 passed
```

Live M4 cutover and rollback:

```text
python -m pytest -q -m integration --basetemp .pytest-m4-live tests/integration/test_m4_gold_cutover.py -s
1 passed in 14.84s
```

The live test verifies persisted-Silver Gold, shadow validation, cross-day current-state updates,
lower-version no-op behaviour, and rollback to legacy Gold without a new Silver snapshot.

Deterministic E2E and repository fast suite:

```text
python -m pytest -q -m e2e --basetemp .pytest-m4-e2e tests/e2e/test_lakehouse_e2e.py -s
1 passed in 112.85s

python -m pytest -q --basetemp .pytest-m4-fast
74 passed, 28 deselected
```

The E2E command requires access to the Docker Engine named pipe and was executed with that access
enabled.

## Residual risks and handoff

- Shadow comparison currently scans the full logical legacy and persisted-Silver states; it is a
  validation tool, not an incremental production reconciliation protocol.
- Gold remains a full overwrite, so every successful cycle may create a Gold snapshot even when
  the logical Gold state is unchanged.
- Persisted Silver schema evolution must keep the business columns used by Gold and shadow
  comparison compatible.
- M3 still assumes one active medallion processor per progress path; multi-writer coordination is
  not implemented.
- M5 remains responsible for binding fitness functions, operational cutover gates, and production
  observability.
- D-3a physical partition/file-sizing optimization remains deferred and is not part of M4.
