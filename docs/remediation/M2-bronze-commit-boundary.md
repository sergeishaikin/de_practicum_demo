# M2 — Bronze commit/progress boundary

Status: **complete**.

M2 fixes F-703 at the Landing-to-Bronze boundary. It establishes Spark's streaming file-sink
commit metadata as the authority for Bronze eligibility while preserving the existing Bronze
`done`/`pending` state and Iceberg snapshot `load-id` recovery protocol. M3 durable medallion
progress and the B2 Silver projection are not part of this milestone.

## Previous behavior

`iceberg/writer/iceberg_writer.py` recursively listed the Landing prefix and treated any parquet
file whose mtime was older than `SETTLE_SECONDS` as ready. The `/_temporary/` path filter was an
additional heuristic, but it did not represent the Structured Streaming FileStreamSink commit
protocol. Consequently, an old parquet orphan left by an incomplete or superseded Spark attempt
could be ingested even when it was absent from Spark's committed output manifest.

## New authority and ownership

Spark FileStreamSink writes versioned records under:

```text
s3://<bucket>/<landing-prefix>/_spark_metadata/<batch-id>
```

The writer now:

1. reads `v1` Spark metadata logs;
2. collects only `add` entries;
3. normalizes `s3://`, `s3a://`, `s3n://`, and S3 bucket/key paths;
4. intersects those committed paths with the live Landing parquet listing;
5. excludes paths already present in the writer's `done` set.

mtime, age, and `_temporary` are no longer commit authorities. A parquet file is eligible only if
Spark's metadata lists it. If the metadata directory is absent or a log is invalid, discovery
fails closed rather than guessing that a file is committed.

Ownership remains deliberately split:

| Concern | Owner | Boundary |
| --- | --- | --- |
| Landing file commit | Spark FileStreamSink | `_spark_metadata` `add` records |
| Bronze append | PyIceberg writer | one append with a generated `load-id` |
| Bronze replay ledger | PyIceberg writer | `done` and `pending` state file |
| Append reconciliation | Iceberg snapshot metadata | `load-id` snapshot summary |
| Domain ordering | Event contract | `business_version`; Kafka offset is transport metadata |

This is still the existing append writer protocol. It is not the M3 Silver progress table or a
new medallion-wide progress service.

## Commit, progress, failure, and recovery semantics

For an eligible batch, the writer persists `pending[load_id]` before the Iceberg append. It marks
the paths `done` and removes the pending entry only after the append returns successfully.

- An old orphan parquet without a Spark metadata `add` record is ignored.
- A committed parquet is eligible regardless of its mtime.
- Repeated discovery of the same committed path is suppressed by `done`.
- A crash before the Iceberg append leaves `pending`; the next run finds no matching snapshot and
  retries the append.
- A crash after the Iceberg append but before state-file completion leaves `pending`; the next run
  finds the matching snapshot `load-id`, marks the paths done, and does not append again.
- The writer reads and appends the full Arrow batch, so `business_version` survives unchanged into
  Bronze.

The boundary is therefore:

```text
Spark committed file metadata
        ↓
eligible Landing parquet
        ↓
pending load-id persisted
        ↓
Iceberg Bronze append
        ↓
snapshot load-id observed / reconciled
        ↓
done paths persisted
```

## Evidence gates

Unit and focused regression evidence:

```text
ruff check ...                         All checks passed
python -m pytest ... focused tests     51 passed
```

The writer tests cover old orphan rejection, current-mtime committed-file eligibility, repeated
discovery suppression, invalid Spark metadata fail-closed behavior, and `business_version`
preservation in `read_batch`.

Live crash/recovery evidence:

```text
python -m pytest -m integration tests/integration/test_crash_recovery.py -s
2 passed in 18.16s
```

Deterministic end-to-end evidence against the running Spark/Kafka/MinIO/Iceberg stack:

```text
python -m pytest -m e2e tests/e2e/test_lakehouse_e2e.py -s
1 passed in 98.84s
```

The E2E path uses the real Spark `_spark_metadata` output and retains the M1 exact
`business_version` distribution assertions across Landing and Bronze.

## Residual risks and deferrals

- The reader is coupled to Spark FileStreamSink metadata version `v1`; a Spark protocol change
  requires a compatibility test and an explicit migration.
- Missing or unreadable metadata fails closed, which protects correctness but can delay ingestion
  until the operational issue is repaired.
- The `done` JSON ledger remains an unbounded writer-local set. Its compaction/retention policy is
  deferred under F-707 and must not discard paths still needed for replay protection.
- Spark metadata retention must outlive the writer's discovery and recovery horizon.
- Equal-version conflicting payload rejection (FF-14), Silver durable progress, targeted Silver
  overwrite, and B2 layout tuning remain later milestones or deferred decisions.

## Handoff

M2 is the checkpoint for M3. The next implementation milestone may build the PyIceberg B2 Silver
projection on this committed Bronze input boundary, with its own durable progress and crash seam.
No production Silver/Gold execution model was changed in M2; it remains the existing full-overwrite
medallion path.
