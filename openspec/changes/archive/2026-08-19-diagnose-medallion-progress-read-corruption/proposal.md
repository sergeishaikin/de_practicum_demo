## Why

The M5 gate has twice read a medallion progress object back as valid JSON
followed by bytes that cannot be in that object:

```text
run 1  test_m4_persisted_silver_gold_shadow_and_rollback
       JSONDecodeError: Extra data: line 1 column 238 (char 237)
       tail resembles a PATH value

run 2  test_a_certified_comparison_is_not_repeated_by_a_later_deployment
       UnicodeDecodeError: can't decode byte 0xc0 in position 240
       tail is binary
```

Two different tests, the same read shape, garbage at the same offset region, and
**different** garbage each time. That is not a flaky timeout; something returns
bytes that were never written. The same read shape is used by the medallion
itself at `iceberg/medallion/iceberg_medallion.py:187` and by the writer at
`iceberg/writer/iceberg_writer.py:201`, so if the fault is in the read path it is
not confined to tests.

Nothing about the cause is established. This change establishes it.

## What Changes

- `tests/support/progress_read_diagnostics.py` — captures, at the moment a
  progress object fails to parse: the object path, the size reported before and
  at open, the raw bytes, their length and digest, the longest valid JSON
  prefix, the bytes immediately after it, a second independent read of the same
  object, and a read of the same object through a different pyarrow read path.
- `tests/support/medallion_harness.py` and
  `tests/integration/test_m4_gold_cutover.py` — both readers call it instead of
  parsing inline.
- `.github/workflows/ci-m5-gates.yml` — uploads the captured bytes on failure.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. `skip_specs: true` — this change establishes a cause and does not alter
what the system must do. A fix, if the evidence calls for one, may warrant its
own requirement, and that is decided after the classification rather than before.

## Impact

The captured bytes are the evidence, so they are written undecoded and uploaded
as-is.

A corrupted read **still fails the test**. The capture re-raises. Nothing here
retries, sleeps, backs off, truncates to the first closing brace, tolerates
trailing bytes, or relaxes an assertion — every one of those would convert a
correctness failure into a hidden flaky path.

**Scope fence, checkable rather than descriptive:**

- `git diff --exit-code iceberg/` stays clean until a cause is established. If
  the evidence proves the defect is in the production read or write path, a
  minimal, local, semantics-preserving fix is in scope, with a regression test.
- No storage-protocol, atomicity-contract, progress-format or business-semantics
  change without a separate decision.
- `04-09` is not started, its output artifact is not created, and no benchmark
  receipt is emulated. No canonical warehouse state is mutated.
- `04-10`'s performance disposition is not revisited because of this diagnosis.
