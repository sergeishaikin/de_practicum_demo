# observability-telemetry Specification Delta

## ADDED Requirements

### Requirement: OTLP telemetry is optional and fail-open

First-party traces and logs SHALL export to the configured Collector over OTLP
when the opt-in telemetry profile is enabled. Existing Prometheus endpoints
SHALL remain available and directly scraped. An unavailable Collector or
telemetry backend SHALL NOT fail, alter or delay canonical data processing
beyond bounded exporter timeouts.

#### Scenario: Collector profile is disabled

- **WHEN** the core Compose graph runs without the telemetry profile
- **THEN** writer, medallion, streaming and existing Prometheus/Grafana paths
  retain their current behaviour
- **AND** no telemetry service is required for canonical processing

#### Scenario: Collector is unavailable

- **WHEN** an instrumented service cannot connect to the Collector
- **THEN** its business operation completes with unchanged results
- **AND** telemetry loss/backpressure is logged and counted

### Requirement: Telemetry identity and propagation are bounded

Every first-party resource SHALL set deterministic `service.name`, stable
`service.namespace` where applicable and a stable deployment-environment
attribute. W3C context propagation across synchronous boundaries and Kafka
headers SHALL be tested against the deployed libraries. Asynchronous consumer
work SHALL use a span link when a parent span would be semantically false.

High-cardinality execution identifiers MAY be trace/log attributes but SHALL
NOT be Prometheus labels; Kafka payloads, secrets and arbitrary PII SHALL NOT be
recorded by default.

#### Scenario: Kafka context is asynchronous

- **WHEN** a consumer processes a message whose W3C context was injected by the
  producer
- **THEN** propagation is decoded from the actual Kafka headers and the
  consumer records a link when parent-child continuity would be false
- **AND** no payload or high-cardinality identifier is added as a metric label

### Requirement: Collector resilience is bounded and observable

Network exporters SHALL declare finite queue capacity and retry horizon. Signal
classes that require restart recovery SHALL use persistent `file_storage` WAL
with an explicit disk budget. Queue-full, retry-timeout, exporter failure,
receiver error and refused/dropped telemetry SHALL be exposed through
Prometheus-scrapable Collector/application metrics.

#### Scenario: Queue capacity is exceeded

- **WHEN** a controlled outage fills the configured queue
- **THEN** telemetry drops within the declared bound
- **AND** queue pressure and drops are observable
- **AND** canonical processing remains correct

### Requirement: Redaction and sampling policy is explicit

Application instrumentation SHALL deny secrets, credentials, auth headers,
connection strings, sensitive SQL literals and full event payloads by default.
Collector filtering/redaction SHALL supplement that discipline. Sampling SHALL
be explicitly configured and SHALL preserve errors and critical-path diagnostics
when sampling is introduced.

#### Scenario: Telemetry contains a denied field

- **WHEN** instrumentation encounters an auth header, credential, sensitive SQL
  literal or full event payload
- **THEN** the field is omitted or redacted before export
- **AND** the bounded local sampling policy retains error and critical-path
  diagnostic spans

### Requirement: Backend routing and metric authority are locked

Applications SHALL send telemetry only to the Collector OTLP boundary. A
backend exporter SHALL be inserted in Collector configuration behind the
named `telemetry-backend` slot; application configuration SHALL NOT name a
Tempo, Loki or vendor endpoint. Existing PostgreSQL durable metrics and
Prometheus application metrics remain authoritative for business and pipeline
operations. Collector self-metrics SHALL be used only for Collector health,
queue, retry and drop diagnostics.

NG-0.4 SHALL NOT enable a `spanmetrics` connector or promote span-derived
metrics to SLO/business-metric authority. Such a change requires explicit
equivalence evidence and a separate authorised change.

#### Scenario: A trace backend is added later

- **WHEN** a separately authorised backend change selects an exporter
- **THEN** it changes Collector configuration behind `telemetry-backend`
- **AND** application OTLP endpoints and Kafka/data contracts remain unchanged

#### Scenario: A span-derived metric is proposed

- **WHEN** a design proposes turning spans into operational or business metrics
- **THEN** NG-0.4 rejects the proposal under the span-metrics lockout
- **AND** the existing Prometheus/PostgreSQL authority remains unchanged
