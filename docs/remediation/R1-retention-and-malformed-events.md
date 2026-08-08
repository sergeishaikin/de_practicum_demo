# Residual Remediation R1 — retention contract and malformed events

Status: live-verified for the current stack; F-301 remains MITIGATED and F-705
is RESOLVED for the tested one-partition source contract.

## F-301 / FF-10

Previously, `MAINTENANCE_RETENTION` was passed directly to Trino while the
writer recovery path used Bronze snapshot summaries as its `load-id`
idempotency evidence. No component checked that those snapshots would still
exist when a writer retried.

The maintenance DAG now reads `MAINTENANCE_RECOVERY_HORIZON` and
`MAINTENANCE_RECOVERY_SAFETY_MARGIN`, then validates at import time that:

```text
MAINTENANCE_RETENTION >
MAINTENANCE_RECOVERY_HORIZON + MAINTENANCE_RECOVERY_SAFETY_MARGIN
```

An invalid deployment therefore fails DAG parsing before `expire_snapshots` or
`remove_orphan_files` can run. The contract supports integer durations in
seconds, minutes, hours, and days. The defaults are `2h > 1h + 15m`; equality
is deliberately rejected because maintenance scheduling and expiry rounding
make an equal boundary unsafe.

The two states remain separate:

- `_spark_metadata` is the Spark file-sink commit authority;
- the writer's state/load-id and Bronze snapshot summary are Bronze ingestion
  recovery evidence;
- the maintenance DAG owns snapshot expiry, but may not configure it at or
  below the declared recovery horizon plus safety margin.

This mitigates F-301 for the current snapshot-summary recovery design. It does
not remove the coupling; moving load-id evidence to a durable outbox would be
the stronger future design.

## F-705

The streaming job previously parsed JSON permissively, filtered null
`order_id`, and set `failOnDataLoss=false`. Both malformed payloads and missing
Kafka offsets could therefore disappear without an owned outcome.

The job now has three explicit dispositions:

1. valid records go to the existing raw landing and PostgreSQL paths;
2. invalid JSON/schema or missing `order_id` records go to the durable
   `orders_dead_letter` parquet prefix with raw payload, reason, Kafka
   timestamp, partition, and offset;
3. every source micro-batch writes an overwrite-by-`batch_id` reconciliation
   receipt under `orders_reconciliation` containing observed, valid, and
   dead-letter counts plus Kafka partition/offset bounds.

`KAFKA_FAIL_ON_DATA_LOSS` defaults to `true`, so unavailable Kafka offsets fail
the query loudly and require operational recovery instead of silently
advancing. The dead-letter and reconciliation queries have their own
checkpoints and are replay-safe at the batch receipt level. The source-window
bounds are used in the live one-partition test to prove that raw offset 0 and
dead-letter offset 1 are exactly the two observed inputs; no equality of
independent query `batch_id` values is assumed.

## Verification

Local checks:

- `python -m pytest tests/test_residual_remediation.py tests/test_order_contract.py -q`
- `ruff check dags/recovery_contract.py dags/lakehouse_maintenance.py spark/jobs/orders_streaming.py tests/test_residual_remediation.py tests/test_dags.py scripts/dump_dag_structure.py`

Live evidence:

- `python -m pytest -m airflow tests/test_dags.py -q` — 8 passed
- Airflow negative import with `MAINTENANCE_RETENTION=75m`,
  `MAINTENANCE_RECOVERY_HORIZON=1h`, `MAINTENANCE_RECOVERY_SAFETY_MARGIN=15m`
  — rejected with the FF-10 contract error
- `python -m pytest -m e2e tests/e2e/test_r1_streaming_e2e.py::test_r1_malformed_event_dead_letter_reconciliation_and_replay -s`
  — passed in 71.01s
- `python -m pytest -m e2e tests/e2e/test_r1_streaming_e2e.py::test_r1_offset_loss_fails_loudly -s`
  — passed in 106.47s

Residual risk: F-301 still couples writer recovery to Bronze snapshot retention;
the strict margin prevents boundary expiry but does not remove that ownership
coupling. F-705 evidence is deterministic for one Kafka partition; a future
multi-partition contract should persist per-partition offset bounds or an exact
source-record manifest before broadening the RESOLVED disposition.
