# NG-0.3 — OpenMetadata Catalog, Lineage and Data UI

> **Lifecycle:** DONE
> **Disposition:** ADOPTED
> **Implemented by:** `add-openmetadata-catalog`
> **Archived change:** `openspec/changes/archive/2026-08-20-add-openmetadata-catalog/`
> **Original role:** pre-implementation specification
>
> **This document is historical intent, not current behaviour.** It records
> what was proposed before implementation. Current truth lives in
> `openspec/specs/`, repository documentation, code, and tests.
> **Execution authorization:** Covered by the bounded `programme:bounded-autonomous-next-generation` authorisation recorded in the repository on 2026-08-19. This file still specifies the change; it does not authorise work beyond that programme.
> **Opens as:** `add-openmetadata-catalog`
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

Adopt **OpenMetadata** as the first integrated data catalog / metadata graph / lineage UI. **DataHub is the fallback candidate, not a co-deployment.** A blocker that would force DataHub evaluation must be documented and measured; both products SHALL NOT be added simultaneously merely for comparison.

OpenMetadata is the **data UI**, not the observability UI. Grafana remains the operational telemetry UI. NG-0.7 will cross-link them instead of building a custom portal prematurely.

## Dependencies

NG-0.1 and NG-0.2.

## Goal

Provide one searchable data asset experience for ownership, schemas, lineage, quality/freshness context, domains/tags and downstream impact while preserving existing runtime and canonical storage ownership.

## Resource constraint

OpenMetadata's local Docker documentation requires substantial resources by itself. Therefore the metadata plane SHALL be an opt-in `metadata` profile and SHALL NOT become part of the core H1 stack.

## Non-goals

- No replacement of Airflow.
- No replacement of dbt.
- No replacement of Grafana.
- No OpenMetadata-managed second Airflow installation.
- No metadata write path into canonical Iceberg or `dwh` business tables.
- No attempt to make the catalog available when the optional profile is not started.
- No simultaneous DataHub/OpenMetadata production demo.

## ADDED Requirements

### Requirement: Isolated control-plane persistence

OpenMetadata SHALL use a dedicated logical database and dedicated credentials. It SHALL NOT store its application tables inside the `dwh` database schemas.

For the local demo, the existing PostgreSQL server MAY host a separate `openmetadata` database if resource and privilege tests pass. Production guidance SHALL treat metadata persistence as independently scalable.

### Requirement: OpenSearch is a supporting dependency, not a new data product

The OpenMetadata profile SHALL use a supported OpenSearch version for search rather than introducing Elasticsearch solely by default. OpenSearch SHALL remain internal to the metadata profile and SHALL NOT become a business data store.

### Requirement: No second Airflow

OpenMetadata SHALL connect to the existing Airflow through its supported REST/API metadata path and receive runtime lineage through NG-0.2.

The implementation SHALL NOT start OpenMetadata's own bundled Airflow merely to run ingestion if equivalent ingestion can be executed from a dedicated lightweight ingestion process/container.

### Requirement: Catalog core assets

The initial catalog scope SHALL include, at minimum where connector support is proven:

- Kafka topics used by the demo;
- PostgreSQL warehouse schemas/tables/views;
- Airflow pipelines;
- Trino and the Iceberg tables visible through the existing catalog;
- dbt models, sources, tests and docs;
- BI assets for the selected existing BI tool where supported.

Any unsupported asset SHALL be listed in an explicit coverage gap table; it SHALL NOT be silently omitted from the claimed E2E lineage.

### Requirement: dbt artifacts enrich, not replace, runtime lineage

The catalog SHALL ingest dbt artifacts needed for model lineage, tests, documentation and column relationships.

`manifest.json`/compiled artifacts SHALL be generated by deterministic CI/workflow steps. A stale developer-local artifact SHALL NOT be treated as current metadata.

### Requirement: Column lineage claims are evidence-backed

Column-level lineage SHALL be declared only for transformations/connectors that actually produce it. Table-level runtime lineage and column-level dbt/static lineage SHALL be visually/semantically distinguishable where necessary.

### Requirement: Ownership and domain metadata are explicit

At least the core demo assets SHALL carry deterministic ownership/domain metadata. Ownership SHALL be configured as code or another reproducible source, not manually entered only in a local UI.

### Requirement: Data quality context is federated

Existing dbt tests/freshness and medallion quality results SHALL remain authoritative in their existing execution systems. OpenMetadata MAY ingest/present them, but SHALL NOT create a second conflicting execution truth.

### Requirement: Runtime lineage is received through OpenLineage

Airflow/runtime lineage from NG-0.2 SHALL arrive through the supported OpenMetadata OpenLineage endpoint/transport. Product-specific direct calls SHALL be limited to metadata not expressible or not supported through the protocol.

### Requirement: Cross-links to observability are stable

Dataset and pipeline entities SHALL expose reproducible deep links or custom metadata pointing to relevant Grafana dashboards/queries once NG-0.7 is complete. OpenMetadata SHALL NOT embed secrets in URLs.

### Requirement: Read-only source credentials

Connectors SHALL use read-only or metadata-minimum privileges against source systems wherever supported. A connector SHALL NOT receive DDL/DML rights merely for convenience.

### Requirement: Metadata profile is optional and bounded

`docker compose` without the metadata profile SHALL retain the current core behavior. The metadata profile SHALL have its own health checks, clean-start smoke and measured resource receipt.

## Non-functional requirements

- **Searchability:** core assets searchable by stable names/tags.
- **Freshness:** ingestion/run metadata latency measured and documented.
- **Security:** independent bot/service credentials; no root/superuser unless proven unavoidable in local-only setup.
- **Resource use:** profile does not cause core tests to exceed their existing resource envelope.
- **Reproducibility:** services/connectors/configuration provisioned as code.
- **Upgradeability:** exact OpenMetadata/OpenSearch versions pinned and compatibility checked before upgrade.
- **Recoverability:** deleting the metadata profile's persistent state and re-ingesting SHALL rebuild the catalog without changing canonical data.

## Acceptance scenarios

#### Scenario: Impact analysis from Gold

- **WHEN** an operator opens `gold.orders_daily_metrics`
- **THEN** upstream datasets/jobs are visible to the extent proved by NG-0.2/dbt ingestion
- **AND** downstream dbt/BI consumers are visible where connectors are supported.

#### Scenario: Metadata database is deleted

- **WHEN** only OpenMetadata/OpenSearch state is removed
- **THEN** canonical Kafka/PostgreSQL/Iceberg state is unchanged
- **AND** the metadata graph can be rebuilt from source metadata/events/configuration.

#### Scenario: Source connector lacks column lineage

- **WHEN** a connector proves only table-level lineage
- **THEN** the UI/spec reports table-level coverage
- **AND** no synthetic column edges are created.

## Acceptance gates

- clean `metadata` profile start from fresh volumes;
- connector coverage inventory with explicit supported/unsupported assets;
- reproducible ownership/tag/domain seeding;
- E2E lineage UI screenshot/evidence artifact for one real run;
- dbt test/freshness metadata visible without altering dbt execution;
- core stack gates remain green with metadata profile off;
- metadata-profile CI green with profile on;
- destroy/rebuild test proves control-plane rebuildability.

## Verified external constraints

At planning time, OpenMetadata 1.12 documentation states local Docker needs at least 6 GiB RAM and 4 vCPUs, and requires PostgreSQL/MySQL plus Elasticsearch/OpenSearch. The implementation SHALL re-verify these constraints and supported versions before pinning images.

## Rollback

Remove/disable the `metadata` profile and its integration configuration. No rollback may require changing Iceberg snapshots or business warehouse contents.

## Hard stops

Stop for architecture approval if OpenMetadata requires canonical write privileges, a replacement Airflow, an unsupported engine downgrade, or a permanent increase to the core H1 resource requirement.
