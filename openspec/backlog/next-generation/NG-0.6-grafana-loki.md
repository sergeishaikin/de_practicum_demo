# NG-0.6 — Grafana Loki Log Backend

> **Lifecycle:** PLANNED
> **Disposition:** pending
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Opens as:** `add-loki-log-backend`
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

Add **Grafana Loki** for centralized structured logs and send OTel-formatted logs through the OpenTelemetry Collector using Loki's native OTLP ingestion path where supported.

## Dependencies

NG-0.4. NG-0.5 is recommended but not technically required.

## Goal

Make first-party service logs centrally searchable and correlatable with trace IDs/run identities while avoiding cardinality explosions and preserving stdout/container logging as a fallback.

## Non-goals

- No replacement of application error handling with log search.
- No ingestion of every Docker daemon log in the first wave.
- No `trace_id`, business key or arbitrary run ID as Loki index labels.
- No direct Loki exporter if native OTLP is supported by the pinned Loki version.
- No secrets/full event payloads in logs.

## ADDED Requirements

### Requirement: Structured logging

First-party services SHALL emit structured logs with deterministic fields for severity, service, event/message, timestamp and available NG-0.1 execution identifiers.

Human-readable text MAY remain, but machine fields SHALL NOT require regex parsing of prose.

### Requirement: Native OTLP ingestion

The Collector SHALL send logs to Loki using the native OTLP-compatible route supported by the pinned Loki version rather than the legacy Loki exporter path.

### Requirement: Low-cardinality labels only

Loki indexed labels SHALL be limited to a reviewed low-cardinality set such as service/environment/severity class where justified. High-cardinality context (`trace_id`, `cycle_id`, `load_id`, object path, business key) SHALL be stored as structured metadata/log fields, not index labels.

### Requirement: Trace correlation

When a log is produced inside an active trace context, it SHALL contain the trace/span correlation fields required for Grafana trace-to-logs navigation.

### Requirement: Redaction is tested

Secrets, passwords, tokens, authorization headers, private connection strings and full unapproved payloads SHALL be redacted or excluded before export.

A negative test SHALL feed representative secret patterns and assert that they do not reach persisted Loki content.

### Requirement: Collection scope is explicit

The first wave SHALL enumerate which services have supported log collection. Unsupported third-party/container logs SHALL remain an explicit coverage gap; implementation SHALL NOT claim "all platform logs" until proven.

### Requirement: Storage isolation and retention

Loki data SHALL use an isolated storage location/prefix and bounded retention. Retention actions SHALL NOT overlap Iceberg or Tempo data.

### Requirement: Backend failure does not block processing

Loki outage SHALL follow NG-0.4 buffering/drop observability behavior and SHALL NOT fail business processing merely because log export is unavailable.

## Non-functional requirements

- **Search latency:** measured for the local demo workload.
- **Cardinality safety:** label-cardinality test/inspection.
- **Security:** redaction and least-privilege storage credentials.
- **Resource use:** measured log volume and retention disk budget.
- **Recoverability:** bounded Collector/Loki outage test.
- **Maintainability:** one documented logging schema for first-party services.

## Acceptance scenarios

#### Scenario: Trace to logs

- **WHEN** an operator opens a Tempo span for `iceberg-medallion`
- **THEN** Grafana can query Loki for correlated logs from the same trace/run
- **AND** no high-cardinality trace ID is required as a Loki label.

#### Scenario: Secret appears in application input

- **WHEN** a known test secret reaches an exception/input path
- **THEN** the persisted log does not contain the secret value
- **AND** useful diagnostic context remains.

## Acceptance gates

- first-party structured log schema tests;
- native OTLP Loki smoke;
- trace-to-logs deep link;
- negative secret test;
- label-cardinality review/test;
- bounded-retention/storage test;
- profile clean-stack CI.

## Rollback

Disable Loki exporter route/datasource. Services continue stdout logging and canonical processing.

## Hard stops

Stop if centralized logging requires privileged host/Docker access broader than the agreed local threat model; scope collection rather than silently mounting sensitive host resources.
