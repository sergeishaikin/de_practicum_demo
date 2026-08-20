# NG-0.5 — Grafana Tempo Trace Backend

> **Lifecycle:** PLANNED
> **Disposition:** pending
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Opens as:** `add-tempo-trace-backend`
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

Add **Grafana Tempo** as the open-source trace backend behind the OpenTelemetry Collector. Continue using the existing Grafana UI.

## Dependencies

NG-0.4.

## Goal

Persist and query distributed traces for data-platform executions and support trace-to-logs / trace-to-metrics navigation without introducing a second operational UI.

## Non-goals

- Tempo is not a lineage catalog.
- Tempo is not a canonical audit database.
- No application exports directly to Tempo.
- No requirement that existing MinIO be a production recommendation.
- No indefinite retention.

## ADDED Requirements

### Requirement: Collector is the only normal write path

Applications SHALL export OTLP to the Collector; the Collector SHALL route traces to Tempo. Direct per-service Tempo configuration SHALL NOT be introduced.

### Requirement: Trace storage is isolated

Trace objects SHALL use a dedicated bucket/prefix and credentials isolated from Iceberg warehouse data. A cleanup/retention action for traces SHALL NOT match the Iceberg warehouse prefix.

### Requirement: Local S3-compatible storage is replaceable

The local demo MAY reuse the existing S3-compatible object store because Tempo supports S3-compatible backends. Configuration SHALL keep endpoint/bucket/credentials externalized so a different object store can replace it without application changes.

The documentation SHALL explicitly state that the chosen local S3-compatible backend is a demo convenience, not a production storage recommendation.

### Requirement: Retention is bounded

Trace retention SHALL be explicitly configured or operationally bounded. The implementation SHALL record expected and measured disk growth under a representative demo workload.

### Requirement: Trace search uses stable attributes

At minimum, traces SHALL be searchable by stable low-cardinality service identity and useful execution context. Search attributes SHALL NOT depend solely on ephemeral container names.

### Requirement: Trace-to-metrics and metrics-to-trace are proven

Grafana SHALL be configured to link Tempo traces with Prometheus metrics. Where exemplars are emitted, a metric exemplar SHALL navigate to its trace.

### Requirement: Trace-to-logs contract is prepared

Tempo/Grafana datasource configuration SHALL expose a trace-to-logs mapping compatible with the Loki fields defined in NG-0.6.

### Requirement: Error traces preserve diagnostic evidence

Exceptions/failures SHALL record error status/events sufficient to identify the failing step without recording secret payloads.

## Non-functional requirements

- **Queryability:** a known trace is retrievable by ID and searchable by service/context.
- **Resource bound:** profile RAM/disk measured.
- **Security:** isolated bucket, no secret attributes.
- **Failure isolation:** Tempo outage does not fail canonical processing.
- **Recoverability:** backend restart and trace ingestion recovery tested through Collector queues.

## Acceptance scenarios

#### Scenario: Metric to trace

- **WHEN** an operator opens a Prometheus panel containing a configured exemplar
- **THEN** Grafana opens the corresponding Tempo trace
- **AND** the trace contains the expected service/run context.

#### Scenario: Tempo unavailable

- **WHEN** Tempo is stopped during a bounded trace workload
- **THEN** canonical processing continues
- **AND** the Collector records queue/exporter pressure
- **AND** recovery behavior matches NG-0.4.

## Acceptance gates

- fresh `observability-next` profile;
- OTLP trace captured end to end;
- TraceQL/query smoke;
- metric exemplar correlation test;
- isolated storage-path assertion;
- retention/disk receipt;
- core H1 unchanged with optional profile disabled.

## Verified external constraint

Current Tempo documentation supports S3-compatible storage and Grafana correlation with Prometheus/Loki. It also warns that local S3-compatible implementations have different production suitability; the spec preserves storage replaceability.

## Rollback

Disable Tempo and its datasource/exporter route. No data-plane rollback is required.

## Hard stops

Stop if trace persistence requires sharing the Iceberg warehouse namespace/retention policy or granting observability services broad canonical-data write privileges.
