## ADDED Requirements

### Requirement: Tempo uses the adopted Collector boundary and isolated storage

Applications SHALL export only to the NG-0.4 Collector OTLP boundary. A future
Tempo backend SHALL be selected behind the Collector's named
`telemetry-backend` slot and SHALL write to a dedicated trace bucket/prefix
with credentials that cannot write the Iceberg warehouse.

#### Scenario: Backend is added

- **WHEN** the separately authorised Tempo profile is enabled
- **THEN** applications retain their existing OTLP endpoint
- **AND** the Collector routes traces through `telemetry-backend`
- **AND** trace cleanup cannot match the canonical Iceberg prefix

### Requirement: Tempo profile is bounded and fail-open

The Tempo profile SHALL be opt-in, use finite retention and measured resource/
disk bounds, and a Tempo or trace-storage outage SHALL NOT alter canonical data
processing. Collector queue, retry and WAL limits remain those adopted by
NG-0.4.

#### Scenario: Tempo is unavailable

- **WHEN** Tempo or its trace store is unavailable during a bounded workload
- **THEN** canonical processing completes unchanged
- **AND** bounded queue/exporter pressure and telemetry loss are observable

### Requirement: Correlation gates are explicit and governed

Grafana SHALL support trace search and a trace-to-metrics link to existing
Prometheus metrics without requiring span-derived metrics. Metrics-to-trace
exemplar proof SHALL NOT be claimed until usable exemplars are present and
their governance is compatible with NG-0.4; absence of exemplars is a blocking
preflight contradiction, not a reason to enable spanmetrics silently.

#### Scenario: Exemplar gate is absent

- **WHEN** no existing Prometheus exemplar can navigate to a trace
- **THEN** implementation readiness is `NO`
- **AND** a separate governance decision is required before implementation
