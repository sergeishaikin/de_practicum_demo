## Why

The H1 clean-rebuild workflow reached its E2E layer for the first time on
2026-08-18 and failed there: `test_r1_offset_loss_fails_loudly` timed out after
180 s waiting for one Kafka record committed before offset loss. Two earlier
layers of that workflow were repaired the same day (a missing secret
substitution, then a PostgreSQL readiness race), so this is the first failure
the workflow has surfaced from a genuinely cold stack rather than from its own
configuration.

The failure is not classified. It could be an invalid warm-state assumption in
the E2E harness, a real Spark/Kafka cold-start correctness defect, or CI
orchestration and timing. Those three lead to completely different remedies, and
the cheapest-looking one — raising a timeout — is also the one that would hide a
correctness defect if the classification is wrong.

## What Changes

- No runtime behaviour changes. This change classifies the failure and produces
  the evidence for that classification.
- It collects: the log of the ad-hoc streaming container the R1 test creates,
  whether the first streaming process created and committed a checkpoint before
  it was removed, the consumer start offset on the second run, the Kafka topic
  offsets and high watermark, and the measured cold-start latency from Spark
  launch to checkpoint readiness compared with a warm run.
- It ends with one recorded classification and a named successor change that
  carries the remedy. If the evidence does not support a classification, that is
  the recorded outcome — not a guess.

## Capabilities

### New Capabilities

None. This change is diagnostic and declares `skip_specs: true`.

### Modified Capabilities

None. A remedy will modify capabilities; classifying a failure does not.

## Impact

- Affected workflow: `.github/workflows/ci-h1-clean.yml`, step `Deterministic E2E`.
- Affected test: `tests/e2e/test_r1_streaming_e2e.py::test_r1_offset_loss_fails_loudly`,
  with helpers in `tests/e2e/test_lakehouse_e2e.py`.
- Systems observed, not modified: Kafka, Spark Structured Streaming, MinIO
  checkpoints.
- Blocks: `close-b2-rollout-decision` (migrated `01-07`), which the operator
  gated behind a green H1.

## Scope fence

Permitted:

- read the ad-hoc streaming container's log
- determine whether the first process created or committed a checkpoint
- determine the consumer/start offset on the second run
- read Kafka topic offsets and high watermark
- measure cold-start latency from Spark launch to checkpoint readiness
- compare the cold and warm execution paths

Forbidden until the failure is classified:

- increasing the 180 s wait
- increasing the `sleep(20)`
- adding retries
- resetting or deleting checkpoints
- weakening the assertion
- changing production Kafka or Spark semantics

## Pre-change evidence

Gathered read-only before the methodology cutover, from run `32191257152` on
`0dfd479` and its uploaded `h1-clean-stack-evidence` artifact. It is recorded
here because it already exists, not because it settles anything.

Timeline from the collected stack log:

```text
22:19:12  topic orders_r1loss4d6bd943 created, initial high watermark 0
22:22:40  topic removed - the test gave up after its 180 s wait
```

Test shape (`tests/e2e/test_r1_streaming_e2e.py:265`):

```text
create topic
start_streaming(max_offsets_per_trigger=1)
sleep(20)
docker_rm(stream)
publish 2 records
start_streaming(max_offsets_per_trigger=1, trigger_seconds=60)
wait 180 s for one landed record
```

Two harness constants assume a warm stack: `sleep(20)` assumes Spark starts
*and* commits a checkpoint inside 20 s, and the restart pairs
`max_offsets_per_trigger=1` with a 60 s trigger, leaving two or three triggers
inside the 180 s budget. Separately, the long-running `orders-streaming` service
logged a `HDFSMetadataLog.<init>` → `S3AFileSystem.getFileStatus` stack on the
same cold start, which is consistent with first-time checkpoint initialisation
against an empty bucket being slower than on a warm one.

```text
Current hypothesis:  warm-state assumption in the harness
Classification:      NOT YET ESTABLISHED
Missing evidence:    logs from the ad-hoc streaming container the R1 test
                     creates - it is started outside compose, so it is absent
                     from the collected stack log
```

The other two E2E tests in that run passed, and every H1 step before
`Deterministic E2E` was green.
