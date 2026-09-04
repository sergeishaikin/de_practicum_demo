# Grafana correlation and SLI/SLO layer

## ADDED Requirements

### Requirement: Correlated operational navigation

The operational UI SHALL provide a tested, repository-provisioned path from an
authoritative metric symptom through an available trace and correlated logs to
execution context, a canonical dataset identity and the proven downstream
impact. A degraded hop SHALL be reported explicitly rather than inferred.

#### Scenario: Controlled incident navigation

- **WHEN** a controlled shadow mismatch appears in the authoritative metric
- **THEN** the operator can follow bounded metric, trace, logs, execution,
  dataset and downstream links
- **AND** an unavailable backend is shown as a degraded hop.

### Requirement: Identity boundaries

The platform SHALL keep resource, trace, execution, dataset and dashboard
identities distinct. `trace_id`, `run_id`, `load_id`, `cycle_id` and dataset FQN
SHALL NOT become Prometheus labels, Loki index labels or unbounded dashboard
variables.

#### Scenario: High-cardinality identity remains metadata

- **WHEN** a dashboard filters an exact trace or load
- **THEN** the identity is applied as a query or structured-field filter
- **AND** the Prometheus/Loki indexed label set remains bounded.

### Requirement: Dataset deep links

Dashboards for a known dataset SHALL expose a credential-free, configured link
based on the deterministic OpenMetadata FQN. OpenMetadata remains the catalog
and lineage authority; Grafana SHALL NOT reproduce the lineage graph.

#### Scenario: Credential-free dataset link

- **WHEN** an operator selects the known Gold dataset
- **THEN** Grafana exposes a configured link based on its canonical FQN
- **AND** the link contains no credentials or bearer tokens.

### Requirement: Existing metric semantics

Dashboard and alert queries SHALL reuse the executable semantics of
`marts.lakehouse_metrics`, including cycle-envelope filtering and the existing
Prometheus exporter interpretation. They SHALL NOT independently reclassify
phase or cycle rows.

#### Scenario: Cycle semantics are preserved

- **WHEN** a dashboard aggregates historical lakehouse metrics
- **THEN** it uses the repository's cycle-envelope interpretation
- **AND** nested phase rows are not double-counted.

### Requirement: SLI dictionary precedes SLO adoption

Each SLI SHALL declare source, query, authority, unit, aggregation, window,
labels, expected cardinality, owner, missing-data semantics, limitations and
threshold status. Thresholds SHALL be marked `MEASURED/ADOPTED` or
`PROVISIONAL/UNMEASURED`; no unmeasured number may be presented as adopted.

#### Scenario: Provisional threshold is visible

- **WHEN** an SLI has no measured evidence period
- **THEN** its threshold is displayed as `PROVISIONAL/UNMEASURED`
- **AND** it is not described as an adopted production SLO.

### Requirement: Freshness is distinct from arrival

Source freshness SHALL NOT claim detection of an absent expected ingestion.
Missing-arrival detection SHALL use a separate authoritative arrival signal;
when that signal is absent, the SLI SHALL be classified
`REQUIRES_NEW_SIGNAL` and no alert SHALL be implemented.

#### Scenario: No ingestion run

- **WHEN** an expected ingestion does not start and no source timestamp exists
- **THEN** source freshness makes no detection claim
- **AND** missing arrival remains a separate unmeasured candidate.

### Requirement: Provisioned and fail-open UI

Required dashboards, datasources, links and candidate alert configuration SHALL
be version-controlled and reproducibly provisioned. Grafana, Prometheus, Tempo,
Loki or OpenMetadata unavailability SHALL degrade navigation only and SHALL NOT
block canonical business processing.

#### Scenario: Grafana outage

- **WHEN** Grafana or a correlation backend is unavailable
- **THEN** canonical Kafka/Spark/Iceberg/PostgreSQL processing continues
- **AND** only UI navigation is degraded.

### Requirement: Bounded alerting and capability evidence

Every alert SHALL name an authoritative metric, condition, window, missing-data
behavior, failure mode, noise source, correlation target and threshold status.
An opt-in capability acceptance SHALL prove provisioning, bounded queries,
correlation, dataset linking, security and fail-open behavior while core H1
remains independent of the optional UI capability.

#### Scenario: Capability receipt

- **WHEN** the optional correlation capability CI runs
- **THEN** it proves provisioning, bounded queries, correlation, links and
  fail-open behavior
- **AND** core H1 remains runnable without the optional UI capability.
