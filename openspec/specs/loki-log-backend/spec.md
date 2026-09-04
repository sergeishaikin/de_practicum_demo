# loki-log-backend Specification

## Purpose

Define the adopted, optional Grafana Loki log capability behind the
OpenTelemetry Collector while preserving canonical processing, stdout fallback,
and existing Prometheus/PostgreSQL metric authority.

## Requirements

### Requirement: First-party structured records and bounded scope

The adopted first wave SHALL emit deterministic OpenTelemetry log records for
the Iceberg writer, Iceberg medallion, and repository-owned observability
exporter. Records SHALL include timestamp, severity, service identity, event
name, and a safe body. Kafka delivery callbacks, Spark driver/executor logs,
Airflow scheduler/provider task logs, and third-party/container-wide logs are
out of scope until separately authorised. Stdout SHALL remain available as a
fallback.

For lifecycle and review purposes, the excluded surfaces are explicitly named
as the Kafka producer, Spark streaming jobs, and Airflow DAG code; they remain
outside the first adopted wave.

#### Scenario: Machine-readable record

- **WHEN** an in-scope service emits an operational event
- **THEN** the persisted record contains the required fields without parsing prose
- **AND** stdout remains available.

### Requirement: Native OTLP ingestion

Applications SHALL send logs only to the OpenTelemetry Collector. The Collector
SHALL route logs to Loki through the pinned version's native OTLP HTTP endpoint;
application configuration SHALL NOT name Loki directly.

#### Scenario: Native route

- **WHEN** the optional Loki profile is enabled
- **THEN** Collector OTLP HTTP export reaches Loki
- **AND** disabling Loki does not alter trace or metrics routes.

### Requirement: Low-cardinality indexing

Loki indexed labels SHALL be limited to the reviewed low-cardinality set:
`service_name`, `service_namespace`, and
`deployment_environment_name`. Trace IDs, run/load IDs, business keys,
offsets, paths, and other high-cardinality context SHALL remain structured
metadata or body fields, not index labels.

#### Scenario: Cardinality review

- **WHEN** a representative workload is ingested
- **THEN** only the reviewed labels are indexed
- **AND** execution identifiers remain structured metadata.

### Requirement: Bidirectional trace correlation

Logs emitted inside an active trace context SHALL preserve the trace and span
correlation fields required for Grafana navigation. Tempo-to-Loki and
Loki-to-Tempo navigation SHALL resolve to the same trace ID.

#### Scenario: Same-trace navigation

- **WHEN** an operator follows trace-to-logs in Grafana
- **THEN** LogQL returns a log carrying the originating trace ID
- **AND** the log link opens that same trace in Tempo.

### Requirement: Persisted redaction

Secrets, credentials, authorization material, private SQL literals, PII, and
unapproved full payloads SHALL be removed or redacted before export and
persistence. Safe load/execution identity MAY remain queryable.

#### Scenario: Forbidden values do not persist

- **WHEN** representative forbidden values reach an in-scope logging path
- **THEN** a query against persisted Loki content finds none of them
- **AND** safe execution context remains.

### Requirement: Isolated finite retention

Loki SHALL use a dedicated storage location and finite Compactor-managed
retention. Loki credentials SHALL not write or delete Iceberg or Tempo data,
and retention actions SHALL not overlap those namespaces.

#### Scenario: Storage boundary

- **WHEN** Loki writes or expires log data
- **THEN** only its dedicated prefix is writable/deletable
- **AND** Iceberg and Tempo prefixes remain untouched.

### Requirement: Fail-open persistent buffering

Loki, object-store, Collector, queue-saturation, and restart failures SHALL NOT
block or alter canonical business processing, stdout, or Prometheus metrics.
The Loki export queue SHALL use the Collector `file_storage` extension and a
bounded `/var/lib/otelcol` volume so pending log batches have an explicit
persistent recovery contract. Queue, retry, exporter-failure, and drop
pressure SHALL remain observable.

#### Scenario: Backend outage

- **WHEN** Loki is unavailable during a business operation
- **THEN** canonical output is unchanged and the operation completes
- **AND** bounded retry/drop/WAL evidence remains observable.

### Requirement: Capability evidence and profile independence

The Loki capability SHALL have a separate opt-in receipt covering exact SHA,
native OTLP, redaction, correlation, storage/retention, cardinality, resource,
and outage/recovery checks. Core H1 SHALL remain Loki-free and continue to pass
with the optional Loki profile disabled. Prometheus application metrics and
PostgreSQL durable metrics remain authoritative; Loki logs SHALL NOT become a
metric or SLO authority.

#### Scenario: Core remains independent

- **WHEN** core H1 runs with the Loki profile disabled
- **THEN** it succeeds without Loki containers or credentials
- **AND** existing Prometheus/PostgreSQL metric authority is unchanged.
