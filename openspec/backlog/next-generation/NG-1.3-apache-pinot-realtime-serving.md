# NG-1.3 — Apache Pinot Real-Time Application Serving

> **Lifecycle:** PLANNED
> **Disposition:** pending
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Opens as:** `evaluate-pinot-realtime-serving`
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

Evaluate **Apache Pinot** only for a capability distinct from ClickHouse: predictable, application-facing, very-low-latency real-time analytical serving over keyed/current-state data.

Pinot is **EXPERIMENTAL** until a concrete API/query workload proves value. If the workload is adequately served by ClickHouse, Pinot SHALL be removed/not adopted.

## Dependencies

NG-1.1 Flink is mandatory for the planned keyed/repartitioned serving stream unless the existing Kafka topic is proven to satisfy Pinot's primary-key partitioning contract without affecting current consumers. NG-1.2 must have a distinct-role review.

## Planned path

```text
Kafka raw orders
  → Flink validate / business-version logic / keyBy(order_id)
  → curated Kafka topic partitioned by order_id
  → Pinot REALTIME upsert table
  → small application analytics API
```

## Non-goals

- No second BI database with the same role as ClickHouse.
- No direct raw topic adoption if partition/business semantics are unproven.
- No Pinot as canonical order state.
- No equal-version conflict resolution by "last arrival wins".
- No core-H1 inclusion.

## ADDED Requirements

### Requirement: Real application query contract exists first

Before provisioning Pinot, the spec implementation SHALL define a small API/query corpus with latency/freshness expectations and a reason those queries are application-facing rather than analyst/ad-hoc queries.

If no distinct workload can be defined, the correct outcome is `DO NOT IMPLEMENT`.

### Requirement: Stream is partitioned by primary key

The input Kafka stream consumed by an upsert table SHALL be partitioned according to Pinot's required primary-key semantics. The chosen hash/partition function and partition count SHALL be explicit and tested.

The implementation SHALL NOT silently repartition the existing source topic in a way that breaks other consumers.

### Requirement: Flink enforces FF-14 before Pinot

For a given `order_id`, a larger `business_version` MAY supersede a lower version. Equal `business_version` with conflicting payload SHALL fail/route to the existing conflict handling before the event reaches Pinot.

Pinot's behavior for equal comparison values SHALL NOT be used as the business tie-breaker.

#### Scenario: Equal version conflicting payload

- **WHEN** two payloads share `order_id` and `business_version` but differ materially
- **THEN** the Flink/pre-serving validation detects FF-14
- **AND** ambiguous records are not allowed to let Pinot choose by ingest order.

### Requirement: Comparison column is business version

If Pinot full upsert is used for current order state, `business_version` SHALL be evaluated as the comparison ordering field or an equivalently proven deterministic ordering field.

Event time SHALL NOT replace business version merely because it is Pinot's default pattern.

### Requirement: Full upsert is preferred for this demo

The initial experiment SHOULD use full upsert with complete current-state rows. Partial upsert SHALL require a separate correctness design because it introduces additional merge semantics.

### Requirement: Serving state is rebuildable

Pinot state SHALL be reconstructable from the curated Kafka/history/source-of-truth. Pinot SHALL not become the only location of current business truth.

### Requirement: Partition capacity is chosen deliberately

Because upsert partitioning has operational consequences, partition count SHALL be set by a documented local capacity/demo requirement and SHALL NOT be presented as a production recommendation.

### Requirement: Resource profile is isolated

Pinot SHALL live behind an opt-in `pinot` profile. It SHALL reuse the existing Kafka. The profile SHALL record measured resource use and SHALL never become a prerequisite for core H1.

### Requirement: ClickHouse distinction is measured

The acceptance report SHALL compare Pinot and ClickHouse for the declared application query corpus where both can answer it, including query latency, ingestion freshness, memory, operational complexity and failure recovery.

Pinot is adopted only if its distinct serving value justifies the extra cluster.

## Non-functional requirements

- application query latency measured as distribution, not one best run;
- bounded stale-data/recovery behavior;
- deterministic keyed semantics;
- isolated credentials/profile;
- query API validates parameters and has its own tests;
- operational metrics/dashboards;
- metadata lineage back to curated Kafka/canonical assets.

## Failure-injection tests

- Pinot server/controller restart;
- Kafka replay;
- Flink restart before/after checkpoint;
- out-of-order lower business version;
- equal-version FF-14 conflict;
- temporary Pinot unavailability while source stream continues;
- rebuild from source.

## Acceptance gates

- distinct API/query contract approved;
- keyed Kafka partition contract test;
- FF-14 negative test before Pinot;
- upsert/current-state parity against canonical Silver;
- restart/replay recovery;
- ClickHouse-vs-Pinot role/benchmark receipt;
- profile clean CI;
- final `ADOPT / KEEP OPTIONAL / REMOVE`.

## Verified external constraints

Current Pinot documentation requires upsert input to be partitioned by primary key and notes that equal primary-key records with equal comparison values do not have deterministic ordering. It explicitly suggests Flink when an input stream must be repartitioned. Its Docker guidance is also resource-heavy, reinforcing the opt-in profile requirement.

## Rollback

Stop Pinot and curated serving consumers; remove projection state. Canonical Kafka/Iceberg data remains unchanged.

## Hard stops

Stop before changing the existing canonical Kafka partition count/keying contract, before allowing Pinot to resolve FF-14 conflicts, or before making Pinot the canonical current-state authority.
