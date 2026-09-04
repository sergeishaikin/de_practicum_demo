# Loki log backend

## ADDED Requirements

### Requirement: First-party structured records

The first-party collection scope SHALL emit deterministic OpenTelemetry log
records with timestamp, severity, service identity, event name and safe body.
The first adopted wave covers the Iceberg writer, Iceberg medallion and
repository-owned observability exporter. Kafka delivery callbacks, Spark
driver/executor logs and Airflow scheduler/provider task logs are explicitly
out of scope until a separately authorised packaging and lifecycle contract is
approved.

#### Scenario: Machine-readable record

- **WHEN** an in-scope service emits an operational event
- **THEN** the persisted record contains the required fields without parsing
  prose
- **AND** stdout remains available as a fallback.

### Requirement: Native OTLP route

The OpenTelemetry Collector SHALL route logs to the pinned Loki version through
the native OTLP HTTP endpoint, while applications send only to the Collector.

#### Scenario: Loki receives OTLP logs

- **WHEN** the Loki capability profile is enabled
- **THEN** a Collector `otlphttp` export reaches Loki's `/otlp` endpoint
- **AND** disabling Loki does not alter the existing trace or metrics routes.

### Requirement: Low-cardinality indexing

Loki index labels SHALL be limited to the reviewed service and environment set.
Trace IDs, run/load IDs, business keys, offsets and paths SHALL remain
structured metadata or body fields.

#### Scenario: Cardinality review

- **WHEN** a representative workload is ingested
- **THEN** the capability receipt lists label names/cardinality
- **AND** no high-cardinality execution identifier is an index label.

### Requirement: Bidirectional trace correlation

Correlated logs SHALL preserve the active trace ID and support Grafana
Tempo-to-Loki and Loki-to-Tempo navigation.

#### Scenario: Same trace navigation

- **WHEN** an operator opens a Tempo span and follows trace-to-logs
- **THEN** LogQL returns a log carrying the same trace ID
- **AND** the log's derived field opens that same trace in Tempo.

### Requirement: Persisted redaction

Secrets, credentials, authorization material, private SQL literals, PII and
unapproved payloads SHALL be removed before export.

#### Scenario: Forbidden values do not persist

- **WHEN** representative forbidden values are sent through an error path
- **THEN** a query against persisted Loki content finds none of them
- **AND** safe load/execution identity remains available.

### Requirement: Isolated finite retention

Loki SHALL use a dedicated storage location and finite Compactor-managed
retention that cannot overlap Iceberg or Tempo data.

#### Scenario: Storage boundary and expiry

- **WHEN** the profile writes and expires log data
- **THEN** only the Loki prefix is writable/deletable by Loki credentials
- **AND** data older than the declared retention is removed without touching
  canonical or Tempo prefixes.

### Requirement: Fail-open observability

Collector, Loki, object-store, queue-saturation and restart failures SHALL NOT
block canonical business processing, stdout or Prometheus metrics.

#### Scenario: Backend outage

- **WHEN** Loki is unavailable during a business operation
- **THEN** the operation completes with unchanged canonical output
- **AND** bounded retry/drop/WAL evidence is recorded.

### Requirement: Capability evidence

The Loki capability SHALL have a separate opt-in CI receipt covering exact SHA,
image digest, native OTLP, redaction, correlation, storage/retention,
cardinality, resource and outage checks; core H1 SHALL remain Loki-free.

#### Scenario: Core remains independent

- **WHEN** core H1 runs without the Loki profile
- **THEN** it succeeds without Loki containers or credentials
- **AND** the capability workflow is the only required Loki runtime gate.
