# tempo-trace-backend Specification

## Purpose

Define the adopted, optional Grafana Tempo trace capability behind the
OpenTelemetry Collector without changing canonical data processing or existing
Prometheus/PostgreSQL metric authority.

## Requirements

### Requirement: Collector-only routing and isolated storage

Applications SHALL send traces destined for Tempo through the Collector OTLP
boundary. Existing Prometheus application metrics SHALL remain directly
scraped. The Collector SHALL route traces through the named
`telemetry-backend` exporter slot; application configuration SHALL NOT name Tempo directly. Tempo SHALL
write to a dedicated trace bucket/prefix with credentials that cannot write the
Iceberg warehouse, and trace cleanup SHALL NOT match the canonical warehouse
prefix.

#### Scenario: Trace backend is enabled

- **WHEN** the optional Tempo profile is enabled
- **THEN** applications continue exporting to the Collector OTLP endpoint
- **AND** the Collector routes traces through `telemetry-backend`
- **AND** a trace credential cannot write the canonical warehouse prefix

### Requirement: Optional bounded profile

The Tempo profile SHALL be opt-in, use finite retention and compaction, and
record bounded resource and disk measurements. A Tempo or trace-storage outage
SHALL NOT alter canonical processing. Collector queue, retry and persistent WAL
limits SHALL remain bounded and observable under outage pressure.

#### Scenario: Trace backend is unavailable

- **WHEN** Tempo or its trace store is stopped during a bounded workload
- **THEN** canonical processing completes with unchanged results
- **AND** bounded queue, retry and WAL pressure remains observable

### Requirement: Queryability and correlation

Tempo SHALL support stable trace search/TraceQL identity and Grafana queryability.
Grafana SHALL expose the provisioned Tempo datasource and trace-to-metrics
navigation to the existing Prometheus datasource. When an existing application
metric emits a bounded `trace_id` exemplar, that exemplar SHALL resolve through
Grafana to the same Tempo trace ID. Exemplar metadata SHALL NOT become a
metric series label or span-derived metric authority.

#### Scenario: Exemplar navigation is correlated

- **WHEN** a sampled trace records an existing Prometheus metric exemplar
- **THEN** Grafana can query the same trace ID through Tempo
- **AND** no new metric series label or span-derived metric is introduced

### Requirement: Redaction and telemetry safety

Application instrumentation SHALL deny secrets, credentials, auth headers,
connection strings, sensitive SQL literals and full event payloads by default.
Collector redaction SHALL supplement that discipline for exported traces and
logs. Safe execution identity MAY remain queryable, while forbidden values
MUST be omitted or redacted before persistence.

#### Scenario: Sensitive trace attributes are exported

- **WHEN** a span contains an auth header, password or sensitive SQL literal
- **THEN** those values are omitted or redacted before Tempo persistence
- **AND** the safe execution load identity remains queryable

### Requirement: Restart and fail-open recovery

Stopping and restarting Tempo or its dedicated trace store SHALL recover the
optional capability without changing canonical data or Kafka/data contracts.
Telemetry loss, queue pressure and exporter failures SHALL remain observable;
canonical processing SHALL remain authoritative during the outage.

#### Scenario: Optional services restart

- **WHEN** Tempo or its dedicated trace store is restarted
- **THEN** the optional capability recovers within its bounded readiness window
- **AND** canonical data and Kafka contracts remain unchanged

### Requirement: Existing authority and future boundaries

Prometheus application metrics and PostgreSQL durable metrics remain the
authoritative operational and business metric paths. Metrics-generator and
spanmetrics are disabled. Trace-to-logs compatibility SHALL remain a prepared
design boundary only; no runtime traces-to-logs mapping is provisioned until
separately authorised NG-0.6. Loki and any NG-0.6 behavior SHALL require a
separate authorised change.

#### Scenario: A log backend is proposed

- **WHEN** trace-to-logs navigation is extended to Loki
- **THEN** it remains outside this capability
- **AND** NG-0.6 authorization is required before implementation
