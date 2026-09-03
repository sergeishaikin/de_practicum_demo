## MODIFIED Requirements

### Requirement: Telemetry identity and propagation are bounded

High-cardinality execution identifiers MAY be trace/log attributes but SHALL
NOT be Prometheus time-series labels or dimensions. `trace_id` and `span_id`
MAY be attached as bounded exemplar metadata to an existing application metric
observation for trace correlation, but exemplar metadata SHALL NOT become
business/SLO grouping authority, increase series cardinality, or justify
span-derived metrics. Kafka payloads, secrets and arbitrary PII SHALL NOT be
recorded by default.

#### Scenario: A trace exemplar annotates an existing metric

- **WHEN** a sampled OTel trace is active during an existing application metric
  observation
- **THEN** the observation MAY carry bounded `trace_id` exemplar metadata
- **AND** `trace_id` is absent from the metric's declared time-series label set
- **AND** the metric value, labels and PostgreSQL durable metric row remain
  unchanged

#### Scenario: Kafka context is asynchronous

- **WHEN** a consumer processes a message whose W3C context was injected by the
  producer
- **THEN** propagation is decoded from the actual Kafka headers and the
  consumer records a link when parent-child continuity would be false
- **AND** no payload or high-cardinality identifier is added as a metric label
