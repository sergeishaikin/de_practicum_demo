# NG-0.7 — Grafana Correlation, Operational UI and SLI/SLO Layer

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

## Product decision

Keep **Grafana** as the operational observability UI and connect Prometheus + Tempo + Loki. OpenMetadata remains the data/catalog UI. The "unified UI" requirement is satisfied first through deliberate cross-linking and consistent identity, not by creating a new custom portal.

## Dependencies

NG-0.3, NG-0.4, NG-0.5, NG-0.6.

## Goal

Allow an operator to move from symptom → metric → trace → logs → affected dataset/lineage with stable links, and introduce evidence-based SLIs/SLOs without inventing thresholds.

## Non-goals

- No replacement of OpenMetadata with Grafana.
- No custom React/portal shell.
- No invented production SLO values.
- No alert based on a metric whose semantics are known to double-count phase/cycle rows.
- No high-cardinality dashboard variables that explode Prometheus/Loki queries.

## ADDED Requirements

### Requirement: Operational UI has three correlated signals

Grafana SHALL provision Prometheus, Tempo and Loki datasources as code and SHALL expose tested navigation among them.

### Requirement: Dataset deep links

Operational dashboards for a known pipeline/dataset SHALL provide a stable link to the corresponding OpenMetadata entity once NG-0.3 is available.

Conversely, OpenMetadata SHALL expose a link back to the relevant Grafana dashboard/query without embedding credentials.

### Requirement: Canonical metric semantics are reused

Existing `marts.lakehouse_metrics` phase/cycle semantics and the current Prometheus interpretation SHALL be reused. Dashboards SHALL NOT re-derive historical classification rules differently from the executable repository contract.

### Requirement: SLIs are defined before SLO thresholds

The platform SHALL define measured SLIs for at least:

- pipeline/run success;
- end-to-end or boundary latency where timestamps are actually available;
- staging/source freshness as distinct from missing-arrival detection;
- streaming lag / checkpoint health where supported;
- metadata/lineage freshness;
- telemetry pipeline health.

An SLO threshold SHALL be marked either `MEASURED/ADOPTED` or `PROVISIONAL/UNMEASURED`. A provisional number SHALL NOT be presented as evidence-backed.

### Requirement: Arrival SLA and freshness are not conflated

The existing source-freshness check only evaluates after ingestion has produced the signal. A missing-ingestion/arrival SLI SHALL be a separate contract if added.

#### Scenario: No ingestion run occurs

- **WHEN** expected source ingestion never starts
- **THEN** the platform SHALL NOT claim that dbt source freshness detected the missing batch
- **AND** any missing-arrival alert must come from a separate arrival/SLA signal.

### Requirement: Correlation workflow is executable

At least one acceptance test/demo SHALL begin from a synthetic/controlled failure and prove navigation:

```text
Grafana alert/panel
  → trace
  → correlated logs
  → run/cycle/load context
  → OpenMetadata dataset
  → downstream impact
```

### Requirement: Dashboards are provisioned

Datasource and dashboard configuration SHALL live in version control. Required acceptance dashboards SHALL NOT depend on manual UI edits.

### Requirement: Alert noise is bounded

Alerts SHALL have documented conditions and a testable reason. A new alert SHALL NOT be created solely because a metric exists.

## Non-functional requirements

- **Usability:** a named incident path can be followed without copying opaque IDs across multiple UIs for every hop.
- **Reproducibility:** dashboards/datasources provisioned from repo.
- **Performance:** dashboard queries bounded and cardinality-reviewed.
- **Security:** no credentials in links/dashboard JSON.
- **Honesty:** unmeasured SLO thresholds visibly provisional.
- **Availability:** Grafana outage does not affect canonical processing.

## Acceptance evidence

- provisioned datasources;
- one end-to-end correlated incident walkthrough;
- metric → trace exemplar proof;
- trace → logs proof;
- Grafana → OpenMetadata link proof;
- SLI dictionary with source, unit, aggregation, owner and threshold status;
- negative scenario proving source freshness is not mislabeled as missing-arrival detection.

## Rollback

Existing Grafana dashboards and Prometheus remain usable if Tempo/Loki/OpenMetadata links are disabled.

## Hard stops

Stop if "single UI" can only be achieved by replacing proven products or building a custom portal before cross-linking has been tested and shown insufficient.
