# NG-1.2 — ClickHouse Hot Operational Analytics

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

Introduce **ClickHouse** for hot, low-latency, analyst/operational analytics. It is a rebuildable serving projection, not a canonical warehouse/lakehouse owner.

This role is intentionally distinct from Apache Pinot in NG-1.3: ClickHouse serves flexible SQL/ad-hoc/dashboard analytics; Pinot is evaluated only for application-facing, predictable low-latency serving/upsert queries.

## Dependencies

NG-0.1 and observability/quality gates; NG-1.1 is preferred because Flink can produce a curated serving stream, but ClickHouse MAY be evaluated directly from an isolated Kafka projection first.

## Goal

Prove whether ClickHouse materially improves a defined hot-query workload over the existing PostgreSQL/Trino paths without duplicating canonical business truth.

## Non-goals

- No replacement of Iceberg.
- No replacement of PostgreSQL/dbt as part of this change.
- No ClickHouse writes to canonical Iceberg.
- No adoption as an observability backend in this wave.
- No claim that materialized views are free.
- No benchmark without identical query semantics and measured denominator.

## ADDED Requirements

### Requirement: ClickHouse data is rebuildable

Every ClickHouse table introduced here SHALL have a documented source-of-truth and replay/rebuild procedure. Deleting ClickHouse state SHALL not destroy the only copy of business data.

### Requirement: Serving workload is declared before schema design

The experiment SHALL define a small query corpus first, such as recent order-state counts, time-window aggregates, country/status slices and operational dashboards.

ORDER BY/partition/materialized-view choices SHALL be justified against those queries, not generic best practices.

### Requirement: Ingestion semantics are explicit

The design SHALL choose and test one ingestion path, for example:

- curated Kafka → ClickHouse;
- Flink → curated Kafka → ClickHouse;
- another bounded OSS mechanism with evidence.

Kafka offset and insert-commit semantics SHALL be failure-tested. "Exactly once" SHALL NOT be claimed unless proven on the selected path/version.

### Requirement: Materialized-view write cost is measured

Incremental materialized views MAY precompute selected rollups, but each added view SHALL have measured ingest/storage cost and query benefit.

A view that does not materially improve the declared workload SHOULD be removed.

### Requirement: Iceberg access is read-only in this phase

ClickHouse MAY query Iceberg for federation/parity/time-travel experiments where supported by the pinned version. It SHALL NOT write to canonical Iceberg in this spec.

### Requirement: Business-version semantics are upstream

ClickHouse SHALL consume records whose business-state semantics are already defined. It SHALL NOT invent an arrival-order conflict rule that contradicts Silver/FF-14.

### Requirement: Benchmark is apples-to-apples

The same logical query and equivalent data state SHALL be compared across relevant engines.

The receipt SHALL include at least:

- data size/rows;
- query corpus;
- warm/cold conditions where applicable;
- p50/p95 (or distribution with repeats);
- ingestion-to-queryable latency;
- concurrency if claimed;
- storage footprint;
- write/merge overhead;
- CPU/RAM.

Absolute ClickHouse speed alone SHALL NOT justify adoption.

### Requirement: Metadata and observability integration

ClickHouse SHALL expose health/query/ingest metrics and be represented in OpenMetadata lineage/catalog where supported. Serving datasets SHALL link back to canonical source assets.

### Requirement: Adoption remains conditional

Final disposition SHALL be `ADOPT`, `KEEP AS OPTIONAL DEMO`, or `REMOVE`. It must answer "what capability does ClickHouse provide here that Trino/PostgreSQL do not provide acceptably?"

## Non-functional requirements

- opt-in `clickhouse` profile;
- exact image version, no `latest`;
- bounded disk and retention for projection;
- least-privilege Kafka/source access;
- deterministic rebuild;
- no impact on canonical source availability during ClickHouse outage;
- benchmark repeatability.

## Acceptance scenarios

#### Scenario: ClickHouse is deleted

- **WHEN** all ClickHouse data volumes are removed
- **THEN** canonical data remains intact
- **AND** the declared projection can be rebuilt from its documented source.

#### Scenario: Duplicate/replay occurs

- **WHEN** the selected ingestion path replays input after failure
- **THEN** final query semantics match the documented contract
- **AND** any duplicate window or dedup mechanism is measured and explicit.

## Acceptance gates

- profile clean start;
- deterministic seed/rebuild;
- failure-injection ingestion test;
- benchmark receipt against at least the relevant existing query path;
- materialized-view cost/benefit receipt if views are used;
- OpenMetadata lineage and Grafana operational link where available;
- repository gates green.

## Verified external constraints

ClickHouse documentation supports Kafka and Iceberg-oriented workflows and describes incremental materialized views as moving computation to insert time with additional write/storage cost. This spec requires that cost to be measured rather than assumed away.

## Rollback

Disable/remove the ClickHouse profile and projection. No canonical rollback is required.

## Hard stops

Stop before ClickHouse becomes the only owner of a business dataset, writes canonical Iceberg, or replaces PostgreSQL/Trino ownership. Such cutover requires a separate architecture/benchmark spec.
