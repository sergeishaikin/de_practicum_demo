# NG-1.1 — Apache Flink Shadow Streaming Path

> **Status:** PROPOSED — future-state specification
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `test/dbt-extensive-testing`
> **SDD convention:** implementation SHALL be opened as its own OpenSpec change with `proposal.md`, `design.md`, `tasks.md`, evidence, and the required spec delta before code is applied.

Normative terms `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are intentional. A requirement is not complete because a container starts; it is complete only when its acceptance evidence is captured and the relevant live CI gates are green.

## Freshness of external assumptions

Versions, compatibility matrices, resource requirements, connector capabilities and product limitations recorded in this item are planning assumptions, not frozen truths. They were recorded against the baseline branch named above and are not re-verified while the item sits in the backlog.

- **WHEN** this item is promoted to an authorised change
- **THEN** every externally time-sensitive premise SHALL be re-verified against primary documentation before the design is accepted
- **AND** a premise that cannot be re-verified SHALL be recorded as unverified rather than carried forward on the authority of this document.

## Product decision

Introduce **Apache Flink** as a shadow/experimental streaming implementation, not an immediate replacement for Spark Structured Streaming.

Compatibility baseline for the first implementation SHALL be **Flink 2.1.x with Apache Iceberg 1.11.x (initially 1.11.0 unless re-verified newer compatible release exists)** because the current Iceberg support matrix explicitly provides a maintained Flink 2.1 runtime. The implementation SHALL NOT select a newer Flink solely because it is the latest if the required Kafka/Iceberg connectors are unavailable.

## Dependencies

NG-0.1 through NG-0.7 and NG-0.9. OpenMetadata is recommended before adoption so lineage impact is visible.

## Goal

Demonstrate and evaluate stateful event-time streaming, watermarks, checkpoints, recovery and a direct Kafka → Flink → Iceberg path while preserving the existing Spark/PyIceberg path as the comparison baseline.

## Initial architecture

```text
existing:
Kafka → Spark Structured Streaming → MinIO landing → PyIceberg writer → bronze.orders

shadow:
Kafka → Flink → bronze_flink.orders (Iceberg)
```

The shadow table/namespace SHALL be physically/logically distinct from canonical Bronze until cutover is separately authorised.

## Non-goals

- No immediate removal of Spark.
- No immediate removal of landing/PyIceberg writer.
- No Flink write into canonical `bronze.orders` in the experiment phase.
- No "exactly once" claim based only on connector docs.
- No change to FF-14 or highest-`business_version` semantics.

## ADDED Requirements

### Requirement: Version compatibility is proven and pinned

The Flink runtime, Kafka connector and Iceberg runtime JAR SHALL be pinned as a tested compatibility set. There SHALL be an automated startup/version assertion.

#### Scenario: latest Flink lacks compatible connector

- **WHEN** the latest Flink release does not have the required Kafka/Iceberg connector build
- **THEN** the project uses the maintained compatible line
- **AND** does not downgrade Iceberg/Spark or compile an unsupported connector without a separate design.

### Requirement: Event-time semantics are explicit

The Flink job SHALL assign event timestamps/watermarks from a defined field and SHALL specify idle-partition behavior.

Late/out-of-order test cases SHALL prove the intended semantics. Processing time SHALL NOT silently substitute for event time.

### Requirement: Stateful business-version behavior is equivalent

If Flink performs dedup/current-state logic, it SHALL preserve the existing business contract:

- larger `business_version` wins for a key;
- transport arrival order does not decide business truth;
- equal `business_version` with conflicting payload triggers FF-14/fail-closed behavior before publishing ambiguous current state.

### Requirement: Checkpointing is durable

Checkpoint storage SHALL use a durable location appropriate to the local stack and SHALL survive the tested JobManager/TaskManager restart scenario.

Checkpoint interval, timeout, retained checkpoints and restart behavior SHALL be explicit.

### Requirement: End-to-end delivery semantics are failure-tested

The project SHALL inject crashes at meaningful points and compare outputs/checkpoints/snapshots. It SHALL claim exactly-once only for the boundaries proven by the combined source/state/sink behavior.

### Requirement: Iceberg sink semantics are direct and isolated

The shadow job SHALL use the supported Iceberg Flink sink and write to a shadow Iceberg table. It SHALL record committed snapshots/checkpoint provenance sufficient for comparison.

### Requirement: Existing Iceberg maintenance is reviewed before Flink adoption

Snapshot expiration/orphan deletion/compaction rules SHALL be tested against the Flink checkpoint/snapshot recovery model. A maintenance action SHALL NOT expire state required to recover the active Flink writer.

No canonical Flink write is authorised until this interaction has an executable fitness test.

### Requirement: Shadow parity is measured

For a deterministic workload, the shadow result SHALL be compared against the existing path for:

- row/business-state parity;
- duplicates/replay behavior;
- FF-14 outcomes;
- late/out-of-order input;
- crash/restart;
- snapshots and file counts;
- end-to-end/event-time latency;
- checkpoint duration/failures;
- resource usage.

### Requirement: OpenLineage/OTel coverage is proven

The Flink job SHALL emit the platform provenance/telemetry required by NG-0.x. Native OpenLineage connector coverage SHALL be tested; missing Iceberg lineage SHALL use a narrow custom event rather than claiming unsupported automatic coverage.

### Requirement: No second Kafka

The Flink profile SHALL reuse the existing Kafka cluster. A second Kafka exists only if a separate isolation test proves it necessary.

### Requirement: Adoption is conditional

Final disposition SHALL be one of:

- `ADOPT AS PRIMARY STREAMING PATH`;
- `KEEP AS OPTIONAL DEMO / SPECIALIZED PATH`;
- `REMOVE / DO NOT ADOPT`.

The decision SHALL cite parity, failure semantics, latency/resource measurements and operational complexity.

## Non-functional requirements

- **Correctness before latency.**
- **Recoverability:** forced failure and deterministic recovery.
- **Resource isolation:** `flink` opt-in profile with measured RAM/CPU.
- **Observability:** checkpoints, backpressure, lag, restarts, throughput, errors visible.
- **Maintainability:** connectors/version matrix documented; no hand-downloaded unverified JAR.
- **Security:** Kafka/S3/catalog credentials scoped as narrowly as local platform permits.

## Acceptance failure matrix

At minimum:

1. kill TaskManager during processing;
2. kill JobManager after a completed checkpoint;
3. restart Kafka consumer path;
4. replay a bounded source range;
5. inject duplicate events;
6. inject lower business version after higher;
7. inject equal-version conflicting payload;
8. inject late/out-of-order event;
9. run maintenance while writer state exists in a controlled fixture;
10. compare shadow table with baseline business state.

## Rollback

Stop/remove Flink profile and shadow table namespace. Existing Spark → landing → PyIceberg path remains untouched and authoritative.

## Hard stops

Stop for explicit authorisation before writing Flink output into canonical `bronze.orders`, deleting/replacing Spark, changing Kafka partitioning for existing consumers, or changing Iceberg maintenance semantics in a way that can delete canonical history.
