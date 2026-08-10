# 01-02B-R — Bounded Kafka Epoch Recovery Proposal

## Status and relationship to historical 01-02B

This is a new recovery proposal dependent on the historical
`01-02B-PLAN.md` result. The historical plan remains **STOP** and must not be
overwritten, reinterpreted as PASS, or marked complete retroactively.

The proposal is planning-only. It performs no runtime action and authorizes no
checkpoint, Kafka, MinIO, Iceberg, PostgreSQL, Docker-volume, or producer
mutation.

## Objective

Determine whether the checkpoint/output epoch conflict can be recovered through
one bounded, auditable path. A recovery may become executable only after all
read-only gates below pass. If any gate is unknown or fails, the outcome is
`STOP`.

## Historical evidence that must remain immutable

- The four existing Spark checkpoint prefixes are preserved.
- The current checkpoint observations terminate at source offset `157`.
- Historical failed-checkpoint evidence records `218961`; committed Landing
  and Bronze output terminates at `kafka_offset=218960`.
- The stable current Kafka observation is partition `0`, offsets `0..40208`
  (`40209` messages), and every observed current payload is absent from Bronze.
- Bronze and Silver each contain `218961` rows and have equal logical
  order/version digests.
- `KAFKA_FAIL_ON_DATA_LOSS=true` remains a safety invariant.

These facts establish the historical STOP; offset equality alone cannot prove
business continuity across Kafka epochs.

## Hard execution gates

### R1 — Read-only recovery preflight

Capture, without changing state:

- Docker control-plane availability and service/container identity;
- Kafka cluster ID, topic identity, partition metadata, and fresh bounds;
- all four checkpoint manifests and terminal offsets;
- current Landing, Bronze, Silver, PostgreSQL, and dead-letter boundaries;
- an inventory of candidate durable canonical replay sources.

R1 fails closed if Docker control-plane access, topic identity, or any
checkpoint evidence is unavailable.

### R2 — Recovery feasibility proof

A candidate replay source must independently prove both properties:

1. **Completeness:** it contains the entire required new event range, with
   canonical payloads and hashes, not merely a count or a successful job run.
2. **Identity/idempotency:** replay events carry a source-generation/epoch
   identity that cannot collide with historical `(topic, partition, offset)`
   values, and the Bronze write path proves duplicate-safe behavior.

R2 must include payload/hash equivalence, event identity, expected Bronze
   coverage, and a deterministic idempotency check. Successful processing alone
   is not evidence of completeness.

### R3 — Preservation barrier

Before any stateful action, record that the following remain unchanged:

- historical checkpoints;
- current Kafka evidence;
- Landing/Bronze/Silver/PostgreSQL state;
- `failOnDataLoss` configuration;
- Docker volumes and topic configuration.

### R4 — New epoch authorization

Only when R1, R2, and R3 pass may a separately named checkpoint epoch be
created. The old checkpoint prefixes remain available for rollback and audit.
The epoch name, source-generation identity, starting boundary, and expected
coverage must be recorded before startup.

### R5 — Sequential stateful recovery

Use one state-mutating executor only. Execute the normal durable Spark recovery
path with `KAFKA_FAIL_ON_DATA_LOSS=true`, then capture every write, checkpoint
advance, Bronze receipt, and rollback decision. No parallel writer may touch the
same runtime state.

### R6 — Read-only post-recovery verification

Verify canonical coverage, source-generation identity, Bronze idempotency,
checkpoint advancement, absence of duplicate business rows, and preservation of
the historical checkpoint. Emit a machine-readable PASS or STOP receipt for the
follow-up verification plan `01-02B-V`.

## Explicit prohibitions

The recovery plan must never permit:

- checkpoint reset, deletion, or overwrite;
- `startingOffsets=latest` as a continuity workaround;
- `failOnDataLoss=false`;
- Kafka topic recreation or truncation;
- destructive Docker volume reset;
- inferred continuity based only on successful processing;
- execution of `01-02C` before post-recovery verification passes.

## Decision outcomes

- `RECOVERED`: R1–R6 pass and a new epoch is proven complete and idempotent.
- `STOP`: any prerequisite, identity proof, completeness proof, or
  preservation check is missing or fails.

`STOP` is a valid terminal outcome and must leave all state unchanged.

## Intended GSD dependency chain

```text
historical 01-02B (STOP)
        ↓
bounded recovery plan 01-02B-R
        ↓
post-recovery verification plan 01-02B-V
        ├─ PASS → 01-02C may be considered
        └─ STOP → remain fail-closed
```

## Expected evidence artifacts

- `artifacts/b2-rollout/02b-recovery-preflight.json`
- `artifacts/b2-rollout/02b-recovery-feasibility.json`
- `artifacts/b2-rollout/02b-recovery-preservation.json`
- `artifacts/b2-rollout/02b-checkpoint-recovery.log`
- `artifacts/b2-rollout/02b-recovery-verification.json`

No application source change is implied by this proposal. Any implementation
change discovered during planning requires a separate reviewed deviation.
