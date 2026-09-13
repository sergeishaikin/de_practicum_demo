# Layer 4 — State, Idempotency and Recovery

## Writer-local state

```text
WriterState {
  done: Set<FilePath>
  pending: Map<LoadId, List<FilePath>>
}
```

The state file is replaced atomically via a temporary file and `os.replace` so readers do not observe a partially written state document.

## Iceberg commit identity

Each successful Bronze append is associated with a `load-id` stored in Iceberg snapshot summary metadata.

This is a stronger recovery signal than the local state file: a process can crash after the Iceberg commit and before local progress is durably updated.

## Recovery rule

```text
pending(load_id)
  -> inspect Bronze snapshots
  -> if snapshot with load-id exists:
       append is already committed
       do not append again
       reconstruct/publish downstream bookkeeping as required
  -> else:
       load has not been committed
       retry is permitted
```

Core invariant:

```text
One logical load_id must not produce a second Bronze append merely because the process crashed after commit.
```

## Bronze outbox

After a committed Bronze load, the writer publishes a durable work record:

```text
BronzeOutboxRecord {
  version
  load_id
  source_paths[]
  bronze_data_files[]
  row_count
}
```

The medallion processor consumes these records as committed units of downstream work.

## Medallion durable state

The medallion path uses multiple durable artifacts:

```text
Progress {
  version
  next_sequence
  work{}
  completed{}
}

CompletionReceipt {
  manifest_id
  load_id
  sequence
  source_paths[]
  source_epoch_id
  completed_at
  result
  silver_snapshot_id
  changed_keys[]
  output_digest
}

ShadowCertificationReceipt {
  version
  ... certification identity/results ...
}
```

Completion receipts are correctness-bearing durable evidence. Ambiguous completion identity is treated as an error rather than silently accepted.

Shadow certification is asymmetric by design: an unreadable or invalid certificate degrades to "not certified", causing comparison work to run again rather than allowing a correctness gate to be skipped.

## Read semantics for mutable JSON state

Small mutable JSON objects in MinIO are read sequentially to EOF. Random-access reads can size themselves from stale object metadata across an overwrite and return an invalid tail. Sequential reads avoid trusting a stale advertised object length.

## Failure-direction principle

Where evidence is ambiguous, the implementation generally fails toward repeating validation/work rather than skipping a correctness gate.

## Traceability anchors

- `iceberg/writer/iceberg_writer.py::load_state`
- `iceberg/writer/iceberg_writer.py::save_state`
- `iceberg/writer/iceberg_writer.py::committed_load_records`
- `iceberg/writer/iceberg_writer.py::recover_pending`
- `iceberg/medallion/iceberg_medallion.py::_read_json`
- `iceberg/medallion/iceberg_medallion.py::load_progress`
- `iceberg/medallion/iceberg_medallion.py::load_completion_ledger`
- `iceberg/medallion/iceberg_medallion.py::load_shadow_receipt`
