# NG-0.8 — Unified Data Reliability: Quality, Freshness, SLA/SLO and Impact

> **Lifecycle:** PLANNED
> **Disposition:** pending
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Opens as:** `unify-data-reliability`
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `test/dbt-extensive-testing`
> **SDD convention:** implementation SHALL be opened as its own OpenSpec change with `proposal.md`, `design.md`, `tasks.md`, evidence, and the required spec delta before code is applied.

Normative terms `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are intentional. A requirement is not complete because a container starts; it is complete only when its acceptance evidence is captured and the relevant live CI gates are green.

## Freshness of external assumptions

Versions, compatibility matrices, resource requirements, connector capabilities and product limitations recorded in this item are planning assumptions, not frozen truths. They were recorded against the baseline branch named above and are not re-verified while the item sits in the backlog.

- **WHEN** this item is promoted to an authorised change
- **THEN** every externally time-sensitive premise SHALL be re-verified against primary documentation before the design is accepted
- **AND** a premise that cannot be re-verified SHALL be recorded as unverified rather than carried forward on the authority of this document.

## Product/capability decision

Do not add a new data-quality product in the first wave. Integrate the repository's existing dbt tests/freshness, medallion quality checks, pipeline outcomes and metadata/observability context through OpenMetadata + Grafana.

A new quality engine is allowed only if a later gap analysis proves an unmet execution capability.

## Dependencies

NG-0.3 and NG-0.7.

## Goal

Turn existing fragmented quality/freshness signals into one governed reliability model without moving execution ownership or duplicating truth.

## Non-goals

- No Great Expectations/Soda/etc. merely for product count.
- No replacement of dbt tests.
- No replacement of medallion checks.
- No conflation of source freshness, arrival SLA, processing latency and business correctness.
- No fabricated historical quality data.

## ADDED Requirements

### Requirement: Quality check ownership is explicit

Each quality rule SHALL declare its execution owner and data boundary, for example:

- dbt source/model test;
- medallion/PyArrow rule;
- warehouse reconciliation;
- architecture/BDD contract;
- future Flink validation.

The catalog/UI MAY aggregate outcomes but SHALL NOT run a duplicate conflicting check under the same identity.

### Requirement: Reliability dimensions are distinct

At minimum the platform SHALL distinguish:

- schema/contract validity;
- completeness/nullability;
- domain validity;
- uniqueness/dedup/business-version semantics;
- reconciliation;
- source load freshness;
- missing-arrival detection (if implemented);
- pipeline success;
- processing latency;
- streaming lag/checkpoint health.

### Requirement: Dataset impact is available

A failed quality/freshness rule SHOULD be linked to the affected dataset and its downstream lineage so an operator can determine blast radius.

### Requirement: Failure severity is encoded

Rules SHALL have explicit severity/behavior (`warn`, `fail closed`, `observe`, etc.) based on existing semantics. The metadata UI SHALL NOT infer severity from display color alone.

### Requirement: Existing fail-closed contracts stay fail-closed

A catalog/observability integration SHALL NOT catch and suppress a quality failure that currently prevents downstream certification.

### Requirement: Historical limitations remain visible

If a metric/rule was not recorded historically, dashboards/catalog SHALL state "not measured" rather than backfilling inferred results.

### Requirement: Reliability state is reproducible

Definitions, mappings, owners and thresholds SHALL be version-controlled. Manual UI-only rule configuration SHALL NOT be the sole source of truth.

### Requirement: Quality to observability correlation

A failed rule SHALL expose enough NG-0.1 identity to find the relevant execution trace/logs where available.

## Non-functional requirements

- no increase in false-success behavior;
- bounded metadata cardinality;
- reproducible configuration;
- no additional write permission to canonical datasets for presentation-only integration;
- all thresholds evidence-backed or explicitly provisional.

## Acceptance scenarios

#### Scenario: dbt freshness fails

- **WHEN** the existing fail-closed freshness check fails
- **THEN** downstream certification remains blocked
- **AND** the failure is visible in operational telemetry
- **AND** the affected source/model lineage is navigable in the catalog.

#### Scenario: Medallion quality warning

- **WHEN** a non-fatal medallion quality rule records violations
- **THEN** the metric/catalog state shows the violation without relabeling the cycle as a hard failure
- **AND** its configured severity is visible.

## Acceptance gates

- reliability dimension registry;
- mappings from existing checks to datasets/owners/severity;
- at least one fail-closed and one observation-only demo;
- downstream impact proof;
- no changed existing quality semantics;
- repository gates green.

## Rollback

Remove presentation/mapping integrations; existing quality execution remains unchanged.

## Hard stops

Stop if unifying quality requires moving a fail-closed rule to a weaker engine, changing business semantics, or mutating historical evidence.
