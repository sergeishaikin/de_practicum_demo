# M3 — B2 Silver projection and durable medallion progress

Status: **implementation complete**.

M3 adds the first stateful medallion path. The existing full-overwrite Silver/Gold path remains
available as `SILVER_MODE=legacy`; M3 does not redesign Gold, remove the legacy path, or implement
M4 shadow rollout/cutover. D-3a physical layout tuning is also outside this milestone.

## Progress ownership and durable representation

The Bronze writer publishes one JSON outbox object after a successful Iceberg Bronze append:

```text
s3://<bucket>/<BRONZE_OUTBOX_PREFIX>/<load_id>.json
```

The object contains the writer load id, source paths, Bronze data-file paths, and row count. The
Bronze snapshot `load-id` remains the writer's append/recovery evidence; the outbox is the durable
handoff to the medallion and is not derived from retained snapshot history.

The B2 processor owns one separate progress object:

```text
s3://<bucket>/<MEDALLION_PROGRESS_PATH>
```

Its bounded state distinguishes:

| State | Durable representation | Meaning |
| --- | --- | --- |
| available | outbox object without a progress entry | committed Bronze work not reserved by Silver |
| in-flight | `progress.work[load_id]` | reserved work whose Silver outcome is not yet durably acknowledged |
| completed | bounded `progress.completed[load_id]` map | Silver result durably acknowledged; stale outbox can be discarded |

Completed entries are sequence-numbered and pruned to `MAX_COMPLETED_PROGRESS` (100 by default).
The control object is compacted as one complete JSON PUT, independent of Iceberg snapshot
retention. The outbox is deleted only after the completed progress record has been durably saved.

## State machine and commit ordering

```text
available outbox
      │ reserve + persist
      ▼
in_flight ── Silver snapshot with work-id found on recovery ──► completed
      │                                                        │
      │ Silver overwrite succeeds                            │ persist completed
      ▼                                                        ▼
completed  ◄────────────── progress commit ─────────────── outbox cleanup
```

For each outbox item the processor:

1. reserves the load id in `progress.work`;
2. reads the committed Bronze data files from the outbox;
3. pre-collapses the incoming rows to one candidate per `order_id` at the greatest
   `business_version`;
4. reads current Silver rows only for the affected `order_id` values;
5. resolves monotonic business versions and calls targeted `overwrite` only for advancing keys;
6. commits Silver with `silver-work-id=<load_id>`;
7. persists completed progress, then deletes the outbox object.

The progress commit is never performed before a successful Silver overwrite for a mutating work
item. A deterministic no-op (lower version or identical replay) has no Silver mutation and may be
acknowledged after proving that the existing Silver state already satisfies the work item.

## B2 correctness and FF-14

The business-key resolver in `iceberg/b2_spike.py` is now shared by production and spike paths.
`business_version` is the only ordering field. `kafka_offset` is retained in the projected row as
transport metadata and is not used to choose the current business state.

Equal `(order_id, business_version)` observations are allowed only when their business payload is
identical. A conflicting payload raises an explicit `ValueError` with the `FF-14` marker before
`Silver.overwrite` is invoked. Lower versions, identical replays, same-batch lower candidates, and
cross-day updates are no-ops or advances according to the business version contract. The targeted
overwrite filter removes every existing row for the affected business key before adding the one
resolved row, preserving global uniqueness.

## Failure and recovery semantics

- Crash before Silver commit: the durable `in_flight` reservation remains, Silver is unchanged,
  and the next run retries the same deterministic work.
- Crash after Silver commit but before progress commit: the reservation remains and the Silver
  snapshot carries the same `silver-work-id`; the next run reconciles it as completed without a
  second overwrite or snapshot.
- Crash after completed progress is saved but before outbox deletion: the next run sees the
  bounded completed marker and deletes the stale outbox without reprocessing.
- Lower-version or identical replay produces no logical Silver change and no new Silver snapshot.
- A failed FF-14 work item remains in-flight and its outbox is retained for explicit remediation;
  no Silver mutation is performed.

## Configuration and scope boundary

The production medallion path is selected explicitly:

```text
SILVER_MODE=legacy  # existing default
SILVER_MODE=b2      # M3 business-key projection
```

`SILVER_MODE=b2` writes Silver only. Gold remains on the legacy full-overwrite path until M4 moves
it to persisted Silver and introduces shadow comparison/cutover. No D-3a bucket/file-sizing
tuning was introduced.

## Verification evidence

PR-tier B2 correctness and state-machine tests:

```text
python -m pytest -q tests/test_b2_medallion.py
6 passed
```

Existing writer and legacy medallion regression tests remained green:

```text
python -m pytest -q --basetemp .pytest-m3-writer tests/test_writer.py tests/test_medallion.py
43 passed
```

Live M3 projection and crash recovery:

```text
python -m pytest -q -m integration tests/integration/test_m3_b2_recovery.py -s
1 passed in 23.21s
```

Repository fast suite and deterministic legacy E2E also remained green:

```text
python -m pytest -q --basetemp .pytest-m3-fast-2
65 passed, 27 deselected

python -m pytest -q -m e2e tests/e2e/test_lakehouse_e2e.py -s
1 passed in 97.59s
```

The live scenario verifies same-batch v3/v5 collapse, cross-day update, lower-version no-op,
multiple keys, exact `business_version`, identical replay without a second snapshot, crash-before
retry, and crash-after reconciliation without a second snapshot.

## Residual risks and M4 handoff

- The outbox and progress objects use S3 object PUT atomicity and assume one active medallion
  processor per progress path. Multi-writer coordination is not implemented.
- A missing Bronze data-file manifest falls back to a full Bronze scan for safety; normal writer
  publication always includes data-file paths.
- Progress retains only the bounded completed window. Operational replay beyond that window relies
  on the outbox having been removed after completion and must not recreate stale outbox objects.
- FF-14 items remain visible as retained in-flight work but have no dead-letter workflow yet.
- Physical locality/file sizing remains the deferred D-3a optimization.
- M4 must read persisted Silver for Gold, run legacy and B2 shadow comparison, and introduce the
  controlled cutover/rollback boundary. M3 intentionally does none of those actions.
