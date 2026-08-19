# NG-0.1 — Platform Provenance and Identity Contract

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

## Goal

Create one cross-system identity and provenance contract before introducing additional metadata, observability, streaming or serving systems. The contract SHALL make a processing result traceable to code, execution, input transport position and canonical Iceberg state without introducing high-cardinality operational failures.

## Context and conflicts

The repository already has useful identities (`run_id`, `ingestion_run_id`, `cycle_id`, `load_id`, Iceberg snapshot IDs, Kafka offsets/checkpoints), but they are not yet one platform contract. OpenTelemetry trace identity is not a replacement for business/run identity; OpenLineage run identity is not a replacement for Airflow or medallion identity. The specification therefore links identifiers rather than forcing all systems to share one UUID.

## Non-goals

- No new metadata UI.
- No tracing backend.
- No change to the business key or `business_version` semantics.
- No change to Iceberg, PostgreSQL or Kafka ownership.
- No attempt to put every identifier into every metric label.
- No new dataset-versioning product.

## ADDED Requirements

### Requirement: Canonical identity vocabulary

The platform SHALL define and document a canonical vocabulary for at least:

- `platform.run_id` — logical execution correlation ID where one exists;
- Airflow `dag_id`, `dag_run_id`, and `task_id`;
- `cycle_id`;
- `load_id`;
- Git commit SHA / build revision;
- OpenTelemetry `trace_id` and `span_id`;
- OpenLineage job namespace/name/run ID;
- dataset namespace/name;
- Kafka topic, partition and offset/range;
- Iceberg table identifier and snapshot ID;
- dbt invocation/model identity where applicable.

The contract SHALL describe which identifier is authoritative for each concern and how cross-references are represented.

#### Scenario: Two systems use different run IDs

- **WHEN** an Airflow task launches or correlates to a downstream processing run
- **THEN** both native identifiers are preserved
- **AND** the relationship is emitted explicitly rather than replacing one identifier with the other.

### Requirement: Provenance envelope

Each first-party data-processing boundary introduced or materially changed after this spec SHALL be able to emit or persist a provenance envelope containing the identifiers available at that boundary.

A provenance envelope SHALL NOT fabricate unavailable values. Unknown identifiers SHALL be absent/null with a documented reason rather than derived from unrelated timestamps or counters.

#### Scenario: No Airflow run exists for a background medallion cycle

- **WHEN** a medallion cycle is not launched by Airflow
- **THEN** `cycle_id`, code revision, dataset and snapshot provenance are recorded
- **AND** no fake `dag_run_id` is created.

### Requirement: Iceberg snapshot is the structured-data version primitive

For structured lakehouse datasets, an Iceberg snapshot ID SHALL be the primary reproducibility reference. DVC or lakeFS SHALL NOT be added solely to version data already reproducibly addressable by Iceberg snapshots.

#### Scenario: An ML experiment consumes Gold data

- **WHEN** the experiment dataset comes from an Iceberg table
- **THEN** the exact table identifier and snapshot ID are stored with the experiment
- **AND** a mutable "latest" table reference alone is insufficient evidence.

### Requirement: Cardinality-safe telemetry

High-cardinality identifiers such as `trace_id`, `span_id`, arbitrary `run_id`, business keys and raw Kafka offsets SHALL NOT become unbounded Prometheus label values.

They MAY appear in structured logs, trace attributes/events, exemplars, OpenLineage facets, evidence artifacts, or bounded tables designed for high-cardinality data.

#### Scenario: A metric must link to a trace

- **WHEN** a latency metric needs drill-down to one representative trace
- **THEN** an exemplar or UI correlation mechanism is used
- **AND** `trace_id` is not added as a permanent series label.

### Requirement: Semantic-convention pinning

Where an external semantic convention is not stable, the emitted convention version/opt-in mode SHALL be explicitly pinned and tested. A dependency upgrade SHALL NOT silently rename telemetry fields.

#### Scenario: Kafka semantic conventions change

- **WHEN** the OpenTelemetry Kafka messaging conventions remain non-stable at the pinned dependency version
- **THEN** the implementation records the emitted convention mode
- **AND** a dependency update that changes field names requires an explicit contract update.

### Requirement: Data-plane/control-plane separation

Metadata, lineage and observability systems SHALL be consumers of data-plane state and events unless a later spec explicitly grants write ownership. Their unavailability SHALL NOT corrupt canonical data or change business-resolution semantics.

#### Scenario: Metadata backend is unavailable

- **WHEN** OpenMetadata or its search engine is down
- **THEN** canonical Kafka → Iceberg or warehouse processing remains semantically correct
- **AND** metadata delivery loss/backlog is observable.

### Requirement: Version and image reproducibility

Every new service image and connector dependency SHALL use an explicit version; critical runtime images SHOULD additionally use a digest where practical. `latest` SHALL NOT appear in committed Compose configuration.

### Requirement: Secrets separation

Credentials for control-plane products SHALL be independent from application superuser credentials wherever the product supports least-privilege access. Secrets SHALL come from environment/secret material and SHALL NOT be committed.

### Requirement: Resource isolation

Every new heavyweight capability SHALL be introduced in an opt-in Compose profile before any proposal to join the default stack. The profile SHALL record measured startup peak RAM, steady-state RAM, CPU and persistent disk use.

### Requirement: Evidence-backed adoption

A technology experiment SHALL terminate in one of `ADOPT`, `KEEP AS OPTIONAL DEMO`, or `REMOVE / DO NOT ADOPT`, with the decision linked to measured requirements rather than popularity.

## Non-functional requirements

- **Correctness:** provenance must identify actual state, never inferred substitutes presented as facts.
- **Availability:** failure of metadata/telemetry must not become a business-data write dependency.
- **Performance:** instrumentation overhead SHALL be measured; no blanket "negligible" claim.
- **Security:** no secrets, full payloads, tokens, credentials or PII in labels/trace attributes by default.
- **Maintainability:** identity mapping lives in one documented module/contract, not ad hoc per service.
- **Compatibility:** existing M5/H1/S1 and recovery semantics remain green.

## Acceptance evidence

- contract document and executable validation for required identity fields;
- negative test proving high-cardinality IDs are absent from Prometheus label sets;
- at least one end-to-end receipt linking Kafka position → processing identity → Iceberg snapshot;
- clean current repository gates;
- no canonical-state mutation required merely to prove the contract.

## Hard stops

Stop for explicit architecture approval if implementation would require changing the canonical business key, Iceberg table ownership, Kafka partitioning contract, persistent progress format, or canonical warehouse schema solely for observability/provenance.
